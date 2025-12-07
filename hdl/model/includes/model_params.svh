// Auto-generated from int8 checkpoint
// source: model/checkpoints/ustc_packet_l2/best_int8.pt
// verilog_format: off
`ifndef MODEL_WEIGHTS_SVH
`define MODEL_WEIGHTS_SVH

package model_params;

localparam int FC_IN_DIM  = 4;
localparam int FC_OUT_DIM = 2;

localparam int CONV1D_1_CHANNEL_OUT_COUNT = 4;
localparam int CONV1D_1_CHANNEL_IN_COUNT  = 1;
localparam int CONV1D_1_KERNEL_WIDTH     = 25;
localparam int CONV1D_1_STRIDE           = 1;

  localparam int WEIGHT_BIT_WIDTH = 8;

  // FC_WEIGHT shape=(2, 4) scale=0.003757536645949356
  localparam int FC_WEIGHT_BIT_WIDTH = 8;
  localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_WEIGHT [0:FC_OUT_DIM-1][0:FC_IN_DIM-1] = '{'{-14, -127, -64, -38}, '{-100, -49, 83, -10}};


  // FC_BIAS shape=(2,) scale=0.004768235946264792
  localparam int FC_BIAS_BIT_WIDTH = 8;
  localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_BIAS [0:FC_OUT_DIM-1] = '{62, -127};


  // CONV1D_1_WEIGHT shape=(4, 1, 25) scale=0.00604618065000519
  localparam int CONV1D_1_WEIGHT_BIT_WIDTH = 8;
  localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_WEIGHT [0:CONV1D_1_CHANNEL_OUT_COUNT-1][0:CONV1D_1_CHANNEL_IN_COUNT-1][0:CONV1D_1_KERNEL_WIDTH-1] = '{'{'{10, -3, -34, 8, -17, -23, -40, 1, 26, 2, 31, 3, 10, 9, 2, 3, 3, 3, -2, 2, -8, -4, -10, 0, 4}}, '{'{-7, -103, -8, -44, -117, -7, -35, 3, -26, -109, 24, -43, 10, -12, -11, 6, -83, 20, 18, 8, 2, 2, 20, -1, -127}}, '{'{-15, 1, -1, 1, 2, 3, -1, 2, 3, -35, 10, -33, -2, 6, 0, -1, 1, 1, 1, 3, 4, 1, 3, 0, -22}}, '{'{-47, -11, 21, 2, 12, 0, -5, 1, -5, 3, 6, 13, 12, -15, 15, 17, 2, 5, 10, -48, -16, 20, -2, 3, -16}}};


  // CONV1D_1_BIAS shape=(4,) scale=0.002849853179586215
  localparam int CONV1D_1_BIAS_BIT_WIDTH = 8;
  localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_BIAS [0:CONV1D_1_CHANNEL_OUT_COUNT-1] = '{3, -127, -46, -79};


endpackage : model_params

`endif // MODEL_WEIGHTS_SVH
// verilog_format: on
