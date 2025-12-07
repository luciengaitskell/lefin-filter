module axis_signer #(
    parameter int INPUT_BIT_WIDTH = 8,
    parameter int INPUT_WIDTH = 4,
    localparam int C_S00_AXIS_TDATA_WIDTH = INPUT_BIT_WIDTH * INPUT_WIDTH,
    localparam int OUTPUT_BIT_WIDTH = INPUT_BIT_WIDTH + 1,
    localparam int OUTPUT_WIDTH = INPUT_WIDTH,
    localparam int C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * OUTPUT_WIDTH
) (
    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [INPUT_WIDTH-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [OUTPUT_WIDTH-1:0] m00_axis_tstrb
);

  logic [INPUT_BIT_WIDTH-1:0] inputs[0:INPUT_WIDTH-1];
  always_comb begin
    for (integer i = 0; i < INPUT_WIDTH; i++) begin
      inputs[i] = s00_axis_tdata[INPUT_BIT_WIDTH*i+:INPUT_BIT_WIDTH];
    end
  end
  always_comb begin
    for (integer i = 0; i < OUTPUT_WIDTH; i++) begin
      m00_axis_tdata[OUTPUT_BIT_WIDTH*i+:OUTPUT_BIT_WIDTH] = {1'b0, inputs[i]};
    end
  end

  assign m00_axis_tvalid = s00_axis_tvalid;
  assign s00_axis_tready = m00_axis_tready;
  assign m00_axis_tlast  = s00_axis_tlast;
  assign m00_axis_tstrb  = s00_axis_tstrb;
endmodule
