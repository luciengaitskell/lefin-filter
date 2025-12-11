
module model_interface #(
    parameter int C_S00_AXIS_TDATA_WIDTH = 32,
    parameter int BIT_WIDTH = 8,
    localparam int WIDTH = C_S00_AXIS_TDATA_WIDTH / BIT_WIDTH,
    localparam int C_M00_AXIS_TDATA_WIDTH = C_S00_AXIS_TDATA_WIDTH,
    parameter int MAXIMUM_INPUT_BYTES = 768,
    parameter int PURGE_CYCLES = 3
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    //  from the Ethernet Subsystem IP
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [WIDTH-1:0] s00_axis_tkeep,  // IP uses tkeep
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [WIDTH-1:0] m00_axis_tstrb
    // we use tstrb in the pipeline as invalid bytes are still retain positional meaning
);

  localparam int MAXIMUM_CYCLES = MAXIMUM_INPUT_BYTES / WIDTH;
  initial begin
    assert (MAXIMUM_CYCLES * WIDTH == MAXIMUM_INPUT_BYTES)
    else
      $error(
          "Error: MAXIMUM_INPUT_BYTES (%0d) must be a multiple of WIDTH (%0d)",
          MAXIMUM_INPUT_BYTES,
          WIDTH
      );
  end

  wire s00_axis_transacted = s00_axis_tvalid && s00_axis_tready;

  logic [$clog2(MAXIMUM_CYCLES+1)-1:0] output_transaction_count;
  wire waiting_for_s00_axis_finish = (output_transaction_count == ($clog2(
      MAXIMUM_CYCLES + 1
  ))'(MAXIMUM_CYCLES));
  logic [$clog2(PURGE_CYCLES+1)-1:0] purge_cycle_count;
  wire purging = purge_cycle_count > 0;
  wire last_cycle = (output_transaction_count == ($clog2(MAXIMUM_CYCLES + 1))'(MAXIMUM_CYCLES - 1));
  wire last_purge = ((purge_cycle_count == ($clog2(
      PURGE_CYCLES + 1
  ))'(PURGE_CYCLES)) || (purging && last_cycle));
  counter #(
      .MAXIMUM  (PURGE_CYCLES + 1),
      .ROLL_OVER(0)
  ) purge_counter (
      .clk(aclk),
      .rst(!aresetn || (last_purge && m00_axis_tready) || waiting_for_s00_axis_finish),
      .trigger((purging && m00_axis_tready && !last_purge) || (!purging && s00_axis_tlast && s00_axis_transacted && !last_cycle)),
      .count(purge_cycle_count)
  );
  counter #(
      .MAXIMUM  (MAXIMUM_CYCLES + 1),
      .ROLL_OVER(0)
  ) output_transaction_counter (
      .clk(aclk),
      .rst    (!aresetn || (s00_axis_tlast && s00_axis_transacted && (output_transaction_count >= ($clog2(
          MAXIMUM_CYCLES + 1
      ))'(MAXIMUM_CYCLES - 1))) || (last_purge && m00_axis_tready)),
      .trigger(((s00_axis_transacted || purging) && !waiting_for_s00_axis_finish)),
      .count(output_transaction_count)
  );

  assign s00_axis_tready = (m00_axis_tready && !purging) || waiting_for_s00_axis_finish;
  assign m00_axis_tvalid = (s00_axis_tvalid && !waiting_for_s00_axis_finish) || (purging);
  assign m00_axis_tstrb  = '1;  // always valid bytes on output
  always_comb begin
    if (purging) begin
      m00_axis_tdata = '0;
    end else begin
      for (int i = 0; i < WIDTH; i++) begin
        if (s00_axis_tkeep[i]) begin
          m00_axis_tdata[BIT_WIDTH*i+:BIT_WIDTH] = s00_axis_tdata[BIT_WIDTH*i+:BIT_WIDTH];
        end else begin
          m00_axis_tdata[BIT_WIDTH*i+:BIT_WIDTH] = '0;
        end
      end
    end
  end

  assign m00_axis_tlast = last_cycle || last_purge;  // one before going into waiting state
endmodule
