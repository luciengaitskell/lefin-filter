module demo_model #(
    parameter integer C_S00_AXIS_TDATA_WIDTH = 32,
    parameter integer INPUT_BIT_WIDTH = 8
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [(C_S00_AXIS_TDATA_WIDTH/INPUT_BIT_WIDTH)-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    output logic classification
);
  localparam integer CHANNEL_OUT_COUNT = 4;
  localparam integer KERNEL_WIDTH = 25;
  localparam integer WEIGHT_BIT_WIDTH = 8;

  localparam signed [WEIGHT_BIT_WIDTH-1:0] weights[0:CHANNEL_OUT_COUNT-1][0:(KERNEL_WIDTH-1)] = '{
      // channel 0
      '{
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1,
          1
      },

      // channel 1
      '{
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2,
          2
      },

      // channel 2
      '{
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3,
          3
      },

      // channel 3
      '{
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4,
          4
      }
  };

  logic m00_axis_tready;
  axis_conv1d #(
      .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .KERNEL_WIDTH          (KERNEL_WIDTH),
      .CHANNEL_OUT_COUNT     (CHANNEL_OUT_COUNT),
      .INPUT_BIT_WIDTH       (INPUT_BIT_WIDTH),
      .WEIGHT_BIT_WIDTH      (WEIGHT_BIT_WIDTH)
  ) axis_conv1d (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .weights        (weights),
      .s00_axis_tlast (s00_axis_tlast),
      .s00_axis_tvalid(s00_axis_tvalid),
      .s00_axis_tdata (s00_axis_tdata),
      .s00_axis_tstrb (s00_axis_tstrb),
      .s00_axis_tready(s00_axis_tready),
      .m00_axis_tready(m00_axis_tready),
      // .m00_axis_tvalid(m00_axis_tvalid),
      // .m00_axis_tlast (m00_axis_tlast),
      // .m00_axis_tstrb (m00_axis_tstrb),
      .m00_axis_tdata (m00_axis_tdata)
  );

    (* keep = "true" *) logic classification_raw;

    assign classification_raw = ^axis_conv1d.m00_axis_tdata;

  assign m00_axis_tready = 1'b1;
  assign classification  = classification_raw;
endmodule
