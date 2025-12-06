module axis_fifo #(
    parameter DATA_WIDTH = 64,
    parameter DEPTH = 1500,
    parameter STRB_WIDTH = DATA_WIDTH / 8,
    parameter KEEP_WIDTH = DATA_WIDTH / 8
) (
    input wire                     aclk,
    input wire                     aresetn,

    // AXIS Slave Interface
    input  wire [DATA_WIDTH-1:0]    s00_axis_tdata,
    input  wire [STRB_WIDTH-1:0]    s00_axis_tstrb,
    input  wire [KEEP_WIDTH-1:0]    s00_axis_tkeep,
    input  wire                     s00_axis_tvalid,
    input  wire                     s00_axis_tlast,
    output logic                    s00_axis_tready,

    // AXIS Master Interface
    output logic [DATA_WIDTH-1:0]    m00_axis_tdata,
    output logic [STRB_WIDTH-1:0]    m00_axis_tstrb,
    output logic [KEEP_WIDTH-1:0]    m00_axis_tkeep,
    output logic                     m00_axis_tvalid,
    output logic                     m00_axis_tlast,
    input  wire                      m00_axis_tready,

    // Read enable single cycle high
    input wire                       packet_output_valid,
    input wire                       packet_output_good
);


// memory declaration
logic [DATA_WIDTH-1:0]    fifo_data_mem [0:DEPTH-1];
logic [STRB_WIDTH-1:0]    fifo_strb_mem [0:DEPTH-1];
logic [KEEP_WIDTH-1:0]    fifo_keep_mem [0:DEPTH-1];
logic [0:0]               fifo_last_mem [0:DEPTH-1];

// read and write pointers
logic [$clog2(DEPTH)-1:0]  write_ptr;
logic [$clog2(DEPTH)-1:0]  read_ptr;


// internal signals declaration
logic valid_input_transaction;
logic valid_output_transaction;
logic read_ptr_equal_write_ptr;
logic valid_data_in_fifo;
logic valid_data_next_round;
logic keep_packet;
logic drop_packet;
// internal signal assignments
assign valid_input_transaction = s00_axis_tvalid && s00_axis_tready;
assign valid_output_transaction = m00_axis_tvalid && m00_axis_tready;
assign read_ptr_equal_write_ptr = (read_ptr == write_ptr);
assign valid_data_in_fifo = read_ptr < write_ptr;
assign valid_data_next_round = (read_ptr + 1) < write_ptr;
assign keep_packet = packet_output_valid && packet_output_good;
assign drop_packet = packet_output_valid && !packet_output_good;

typedef enum logic [2:0] {
    NFILL_NDRAIN,
    FILL_ONLY,
    DRAIN_ONLY,
    FILL_AND_DRAIN,
    FILL_THEN_DROP
} state_t;
state_t cur_state;

// for reads to be on same cycle
always_comb begin
    m00_axis_tdata = fifo_data_mem[read_ptr];
    m00_axis_tstrb = fifo_strb_mem[read_ptr];
    m00_axis_tkeep = fifo_keep_mem[read_ptr];
    m00_axis_tlast = fifo_last_mem[read_ptr];
end


always_ff @(posedge aclk) begin
    if (!aresetn) begin
        // Reset logic
        read_ptr <= 0;
        write_ptr <= 0;
        cur_state <= FILL_ONLY;
        m00_axis_tvalid <= 0;
        s00_axis_tready <= 1;
    end else begin
        // FIFO operation logic
        // Behavior: if tlast comes in, wait until all data is read out before accepting new data
        // Behavior: don't begin reading out data until 
        
        // handle states
        case (cur_state)
            // wait for tlast or read enable 
            FILL_ONLY: begin 
                // handle transition
                case ({packet_output_valid, packet_output_good, s00_axis_tlast})
                    3'b000: begin
                        // stay in FILL_ONLY
                        s00_axis_tready <= 1;
                        m00_axis_tvalid <= 0;
                    end
                    3'b110: begin // keep_packet only
                        cur_state <= FILL_AND_DRAIN;
                        read_ptr <= 0; // reset read pointer
                        s00_axis_tready <= 1;
                        m00_axis_tvalid <= (valid_data_in_fifo);;
                    end
                    3'b100: begin // drop_packet only
                        cur_state <= FILL_THEN_DROP;
                        read_ptr <= 0; // reset read pointer
                        s00_axis_tready <= 1;
                        m00_axis_tvalid <= 0;
                    end
                    3'b001: begin // tlast only
                        cur_state <= NFILL_NDRAIN;
                        read_ptr <= 0; // reset read pointer
                        s00_axis_tready <= 0;
                        m00_axis_tvalid <= 0;
                    end
                    3'b111: begin // keep_packet and tlast
                        cur_state <= DRAIN_ONLY;
                        read_ptr <= 0; // reset read pointer
                        s00_axis_tready <= 0;
                        m00_axis_tvalid <= 1;
                    end
                    3'b101: begin // drop_packet and tlast
                        cur_state <= FILL_ONLY; // RESET FIFO
                        read_ptr <= 0; // reset read pointer
                        write_ptr <= 0; // reset write pointer  
                        s00_axis_tready <= 1;
                        m00_axis_tvalid <= 0;
                    end
                    default: begin
                        // stay in FILL_ONLY
                        s00_axis_tready <= 1;
                        m00_axis_tvalid <= 0;
                    end
                endcase
                // handle writes 
                if (valid_input_transaction) begin
                    fifo_data_mem[write_ptr] <= s00_axis_tdata;
                    fifo_strb_mem[write_ptr] <= s00_axis_tstrb;
                    fifo_keep_mem[write_ptr] <= s00_axis_tkeep;
                    fifo_last_mem[write_ptr] <= s00_axis_tlast;
                    write_ptr <= write_ptr + 1;
                end 
            end
            // wait for all data to be read out
            DRAIN_ONLY: begin
                // handle transition
                if (valid_output_transaction && (fifo_last_mem[read_ptr] == 1'b1)) begin // transacts and last data read indicated by tlast in memory
                    cur_state <= FILL_ONLY;
                    write_ptr <= 0; // reset write pointer
                    read_ptr <= 0; // reset read pointer
                    s00_axis_tready <= 1;
                    m00_axis_tvalid <= 0;
                end else if (valid_output_transaction) begin
                    read_ptr <= read_ptr + 1;
                    // advance read pointer if valid transaction on m_axis
                end
                if (read_ptr > write_ptr) begin
                    // safety check to avoid reading invalid data drop everything and go to FILL_ONLY
                    cur_state <= FILL_ONLY;
                    write_ptr <= 0; // reset write pointer
                    read_ptr <= 0; // reset read pointer
                    s00_axis_tready <= 1;
                    m00_axis_tvalid <= 0;
                    $display("WARNING: AXIS FIFO read pointer exceeded write pointer, resetting FIFO to FILL_ONLY state");
                end
            end
            // wait for tlast to be seen
            FILL_AND_DRAIN: begin 
                // drive ready and valid signals THIS ORDER MATTERS FOR S_TREADY
                s00_axis_tready <= 1;
                m00_axis_tvalid <= (valid_data_next_round); // only valid if there is data to read
                // handle transition
                if (valid_input_transaction && s00_axis_tlast) begin
                    cur_state <= DRAIN_ONLY;
                    s00_axis_tready <= 0;   
                    m00_axis_tvalid <= 1;
                end 
                // handle writes
                if (valid_input_transaction) begin
                    fifo_data_mem[write_ptr] <= s00_axis_tdata;
                    fifo_strb_mem[write_ptr] <= s00_axis_tstrb;
                    fifo_keep_mem[write_ptr] <= s00_axis_tkeep;
                    fifo_last_mem[write_ptr] <= s00_axis_tlast;
                    write_ptr <= write_ptr + 1;
                end
                // handle reads
                // advance read pointer if valid transaction on m_axis
                if (valid_output_transaction) begin
                    read_ptr <= read_ptr + 1;
                end
            end
            // wait for read enable
            NFILL_NDRAIN: begin 
                // handle transition
                if (keep_packet) begin
                    cur_state <= DRAIN_ONLY;
                    s00_axis_tready <= 0;
                    m00_axis_tvalid <= 1;
                end else if (drop_packet) begin
                    cur_state <= FILL_ONLY;
                    write_ptr <= 0; // reset write pointer
                    read_ptr <= 0; // reset read pointer
                    s00_axis_tready <= 1;
                    m00_axis_tvalid <= 0;
                end
            end
            // wait for a tlast to reset, send no data out
            FILL_THEN_DROP: begin 
                // handle transition
                if (valid_input_transaction && s00_axis_tlast) begin
                    cur_state <= FILL_ONLY;
                    write_ptr <= 0; // reset write pointer
                    read_ptr <= 0; // reset read pointer
                    s00_axis_tready <= 1;
                    m00_axis_tvalid <= 0;
                end 
            end

            default: begin
                cur_state <= FILL_ONLY; 
                s00_axis_tready <= 1;
                m00_axis_tvalid <= 0;
                read_ptr <= 0;
                write_ptr <= 0;
            end
        endcase
    end
end
endmodule
