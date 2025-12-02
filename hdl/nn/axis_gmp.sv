
module axis_gmp #(
    parameter int WIDTH = 4,
    parameter int BIT_WIDTH = 8,
    parameter int CHANNEL_COUNT = 1,
    localparam int C_S00_AXIS_TDATA_WIDTH = BIT_WIDTH * WIDTH * CHANNEL_COUNT,
    localparam int C_M00_AXIS_TDATA_WIDTH = BIT_WIDTH * CHANNEL_COUNT
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [(C_S00_AXIS_TDATA_WIDTH/BIT_WIDTH)-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [(C_M00_AXIS_TDATA_WIDTH/BIT_WIDTH)-1:0] m00_axis_tstrb
);

  logic signed [BIT_WIDTH-1:0] inputs[0:CHANNEL_COUNT-1][0:WIDTH-1];
  always_comb begin
    for (integer i = 0; i < WIDTH; i++) begin
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        inputs[channel][i] = s00_axis_tdata[BIT_WIDTH*(channel*WIDTH+i)+:BIT_WIDTH];
      end
    end
  end

  logic signed [BIT_WIDTH-1:0] maximums[0:CHANNEL_COUNT-1];
  always_comb begin
    for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
      m00_axis_tdata[BIT_WIDTH*channel+:BIT_WIDTH] = maximums[channel];
    end
  end


  assign m00_axis_tstrb = '1;
  assign m00_axis_tlast = s00_axis_tlast;
  wire m00_axis_transacted = m00_axis_tready && m00_axis_tvalid;
  assign s00_axis_tready = !m00_axis_tvalid || m00_axis_transacted;
  wire  s00_axis_transacted = s00_axis_tready && s00_axis_tvalid;

  logic was_last;

  always_ff @(posedge aclk) begin
    if (!aresetn) begin
      was_last <= 1'b1;
    end else begin
      if (s00_axis_tlast) begin
        was_last <= s00_axis_tlast;
      end
    end
  end

  always_ff @(posedge aclk) begin
    if (!aresetn) begin
      m00_axis_tvalid <= 1'b0;
    end else begin
      if (s00_axis_tlast) begin
        m00_axis_tvalid <= 1'b1;
      end else if (m00_axis_transacted) begin
        m00_axis_tvalid <= 1'b0;
      end
    end
  end

  always_ff @(posedge aclk) begin
    if (s00_axis_transacted) begin
      if (was_last) begin
        was_last <= 1'b0;
      end
      for (integer channel = 0; channel < CHANNEL_COUNT; channel++) begin
        logic signed [BIT_WIDTH-1:0] channel_max;
        if (was_last) begin
          channel_max = '0;
        end else begin
          channel_max = maximums[channel];
        end
        for (integer i = 0; i < WIDTH; i++) begin
          if (inputs[channel][i] > channel_max) begin
            channel_max = inputs[channel][i];
          end
        end
        maximums[channel] <= channel_max;
      end
    end
  end
endmodule
