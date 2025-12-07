// compares two inputs half of axistream and outputs necessary outputs for fifo control on tlast
module axis_comparator #
(
    parameter DATA_WIDTH = 16,
    localparam C_S00_AXIS_TDATA_WIDTH = DATA_WIDTH * 2
)(
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [C_S00_AXIS_TDATA_WIDTH/2-1:0] s00_axis_tstrb,
    input wire s00_axis_tlast,
    output logic s00_axis_tready,

    // outputs non-axi
    output logic output_valid,
    output logic top_half_greater
);

    // internal signals
    logic signed [DATA_WIDTH-1:0] top_half;
    logic signed [DATA_WIDTH-1:0] bottom_half;

    // split inputs
    always_comb begin
        top_half = $signed(s00_axis_tdata[C_S00_AXIS_TDATA_WIDTH-1 -: DATA_WIDTH]);
        bottom_half = $signed(s00_axis_tdata[DATA_WIDTH-1 -: DATA_WIDTH]);
    end

    // compare
    always_ff @(posedge aclk) begin
        top_half_greater <= (top_half >= bottom_half);
        output_valid <= s00_axis_tvalid && s00_axis_tlast;
    end

    // ready signal always high
    assign s00_axis_tready = 1'b1;
endmodule
