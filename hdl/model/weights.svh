// Auto-generated from int8 checkpoint
// source: final/demo/models/ustc_packet_l2/best_int8.pt
`ifndef MODEL_WEIGHTS_SVH
`define MODEL_WEIGHTS_SVH

localparam int FC_IN_DIM  = 4;
localparam int FC_OUT_DIM = 2;

localparam int CONV1D_1_CHANNEL_OUT_COUNT = 4;
localparam int CONV1D_1_CHANNEL_IN_COUNT  = 1;
localparam int CONV1D_1_KERNEL_WIDTH     = 25;
localparam int CONV1D_1_STRIDE           = 1;

localparam int WEIGHT_BIT_WIDTH = 8;

// FC_WEIGHT shape=(2, 4) scale=0.003865233321828166
localparam real FC_WEIGHT_SCALE = 0.00386523;
localparam int FC_WEIGHT_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_WEIGHT [0:FC_OUT_DIM-1][0:FC_IN_DIM-1] = '{'{17, -123, -50, -43}, '{-127, -47, 70, -4}};


// FC_BIAS shape=(2,) scale=0.006236475283705343
localparam real FC_BIAS_SCALE = 0.00623648;
localparam int FC_BIAS_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_BIAS [0:FC_OUT_DIM-1] = '{77, -127};


// CONV1D_1_WEIGHT shape=(4, 1, 25) scale=0.009514057730126568
localparam real CONV1D_1_WEIGHT_SCALE = 0.00951406;
localparam int CONV1D_1_WEIGHT_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_WEIGHT [0:CONV1D_1_CHANNEL_OUT_COUNT-1][0:CONV1D_1_CHANNEL_IN_COUNT-1][0:CONV1D_1_KERNEL_WIDTH-1] = '{'{'{-14, -39, -55, -7, 15, -32, -50, -10, 1, -12, 6, -11, -14, 6, 5, 4, 9, -13, -7, -10, 9, 7, -32, -18, 8}}, '{'{-5, -111, -6, -21, -118, 0, -13, 2, -11, -127, 10, -21, 5, -9, 2, 4, -52, 9, 13, 4, -3, -3, 10, 1, -94}}, '{'{-19, 2, 1, -3, 4, 3, 0, 0, 3, -55, 9, -38, 2, 7, -2, -4, 1, 1, -2, 1, 3, -1, 3, 2, -13}}, '{'{-74, 0, 12, 6, 3, 0, 3, -5, -3, 3, 4, -4, 2, -7, -1, 11, 1, -10, 2, -56, -10, 12, -3, 2, -3}}};


// CONV1D_1_BIAS shape=(4,) scale=0.00425634609432671
localparam real CONV1D_1_BIAS_SCALE = 0.00425635;
localparam int CONV1D_1_BIAS_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_BIAS [0:CONV1D_1_CHANNEL_OUT_COUNT-1] = '{36, -127, -70, -83};


`endif // MODEL_WEIGHTS_SVH
