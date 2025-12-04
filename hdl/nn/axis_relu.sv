
module axis_relu #(
    parameter integer C_S00_AXIS_TDATA_WIDTH = 32,
    parameter integer BIT_WIDTH = 8,
    parameter integer CHANNEL_COUNT = 1,
    localparam integer NUM_VALUES = C_S00_AXIS_TDATA_WIDTH / BIT_WIDTH,
    localparam integer WIDTH = C_S00_AXIS_TDATA_WIDTH / (CHANNEL_COUNT * BIT_WIDTH),
    localparam integer C_M00_AXIS_TDATA_WIDTH = C_S00_AXIS_TDATA_WIDTH
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [NUM_VALUES-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [(C_M00_AXIS_TDATA_WIDTH/8)-1:0] m00_axis_tstrb
);

  logic signed [BIT_WIDTH-1:0] inputs[0:CHANNEL_COUNT-1][0:WIDTH-1];
  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        inputs[channel][i] = s00_axis_tdata[BIT_WIDTH*(channel*WIDTH+i)+:BIT_WIDTH];
      end
    end
  end

  logic signed [BIT_WIDTH-1:0] outputs[0:CHANNEL_COUNT-1][0:WIDTH-1];
  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        m00_axis_tdata[BIT_WIDTH*(channel*WIDTH+i)+:BIT_WIDTH] = outputs[channel][i];
      end
    end
  end

  assign m00_axis_tstrb  = s00_axis_tstrb;
  assign s00_axis_tready = m00_axis_tready;
  assign m00_axis_tvalid = s00_axis_tvalid;
  assign m00_axis_tlast  = s00_axis_tlast;

  always_comb begin
    for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
      for (integer i = 0; i < WIDTH; i++) begin
        outputs[channel][i] = (inputs[channel][i] > 0) ? inputs[channel][i] : '0;
      end
    end
  end
endmodule
