
module axis_conv1d #(
    parameter int WIDTH = 4,
    parameter int BIT_WIDTH = 8,
    parameter int CHANNEL_COUNT = 1,
    localparam int C_S00_AXIS_TDATA_WIDTH = BIT_WIDTH * WIDTH * CHANNEL_COUNT,
    localparam int C_M00_AXIS_TDATA_WIDTH = BIT_WIDTH * WIDTH * CHANNEL_COUNT
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [WIDTH-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [WIDTH-1:0] m00_axis_tstrb
);

  logic signed [BIT_WIDTH-1:0] inputs[0:WIDTH-1][0:CHANNEL_COUNT-1];
  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        inputs[i][channel] = s00_axis_tdata[BIT_WIDTH*(channel*WIDTH+i)+:BIT_WIDTH];
      end
    end
  end

  logic signed [BIT_WIDTH-1:0] outputs[0:WIDTH-1][0:CHANNEL_COUNT-1];
  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        m00_axis_tdata[BIT_WIDTH*(channel*WIDTH+i)+:BIT_WIDTH] = outputs[i][channel];
      end
    end
  end

  assign m00_axis_tstrb  = s00_axis_tstrb;
  assign s00_axis_tready = m00_axis_tready;
  assign m00_axis_tvalid = s00_axis_tvalid;
  assign m00_axis_tlast  = s00_axis_tlast;

  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        outputs[i][channel] = inputs[i][channel];  // Pass-through
      end
    end
  end
endmodule
