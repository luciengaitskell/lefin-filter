// Auto-generated from int8 checkpoint
// source: final/demo/models/ustc_packet_l2/best_int8.pt
`ifndef MODEL_WEIGHTS_SVH
`define MODEL_WEIGHTS_SVH

localparam int CONV1D_1_CHANNEL_OUT_COUNT = 4;
localparam int CONV1D_1_CHANNEL_IN_COUNT  = 1;
localparam int CONV1D_1_KERNEL_WIDTH     = 25;
localparam int CONV1D_1_STRIDE           = 1;

localparam int FC_1_IN_DIM  = 4;
localparam int FC_1_OUT_DIM = 2;

localparam int WEIGHT_BIT_WIDTH = 8;

// CONV1D_1_WEIGHT shape=(4, 1, 25) scale=0.009514057730126568
localparam real CONV1D_1_WEIGHT_SCALE = 0.00951406;
localparam int CONV1D_1_WEIGHT_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_WEIGHT [0:CONV1D_1_CHANNEL_OUT_COUNT-1][0:CONV1D_1_KERNEL_WIDTH-1] = {{8'sd-14, 8'sd-39, 8'sd-55, 8'sd-7, 8'sd15, 8'sd-32, 8'sd-50, 8'sd-10, 8'sd1, 8'sd-12, 8'sd6, 8'sd-11, 8'sd-14, 8'sd6, 8'sd5, 8'sd4, 8'sd9, 8'sd-13, 8'sd-7, 8'sd-10, 8'sd9, 8'sd7, 8'sd-32, 8'sd-18, 8'sd8}}, {{8'sd-5, 8'sd-111, 8'sd-6, 8'sd-21, 8'sd-118, 8'sd0, 8'sd-13, 8'sd2, 8'sd-11, 8'sd-127, 8'sd10, 8'sd-21, 8'sd5, 8'sd-9, 8'sd2, 8'sd4, 8'sd-52, 8'sd9, 8'sd13, 8'sd4, 8'sd-3, 8'sd-3, 8'sd10, 8'sd1, 8'sd-94}}, {{8'sd-19, 8'sd2, 8'sd1, 8'sd-3, 8'sd4, 8'sd3, 8'sd0, 8'sd0, 8'sd3, 8'sd-55, 8'sd9, 8'sd-38, 8'sd2, 8'sd7, 8'sd-2, 8'sd-4, 8'sd1, 8'sd1, 8'sd-2, 8'sd1, 8'sd3, 8'sd-1, 8'sd3, 8'sd2, 8'sd-13}}, {{8'sd-74, 8'sd0, 8'sd12, 8'sd6, 8'sd3, 8'sd0, 8'sd3, 8'sd-5, 8'sd-3, 8'sd3, 8'sd4, 8'sd-4, 8'sd2, 8'sd-7, 8'sd-1, 8'sd11, 8'sd1, 8'sd-10, 8'sd2, 8'sd-56, 8'sd-10, 8'sd12, 8'sd-3, 8'sd2, 8'sd-3}};


// CONV1D_1_BIAS shape=(4,) scale=0.00425634609432671
localparam real CONV1D_1_BIAS_SCALE = 0.00425635;
localparam int CONV1D_1_BIAS_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] CONV1D_1_BIAS [0:CONV1D_1_CHANNEL_OUT_COUNT-1] = {8'sd36, 8'sd-127, 8'sd-70, 8'sd-83};


// FC_1_WEIGHT shape=(2, 4) scale=0.003865233321828166
localparam real FC_1_WEIGHT_SCALE = 0.00386523;
localparam int FC_1_WEIGHT_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_1_WEIGHT [0:FC_1_OUT_DIM-1][0:FC_1_IN_DIM-1] = {{8'sd17, 8'sd-123, 8'sd-50, 8'sd-43}, {8'sd-127, 8'sd-47, 8'sd70, 8'sd-4}};


// FC_1_BIAS shape=(2,) scale=0.006236475283705343
localparam real FC_1_BIAS_SCALE = 0.00623648;
localparam int FC_1_BIAS_BIT_WIDTH = 8;
localparam signed [WEIGHT_BIT_WIDTH-1:0] FC_1_BIAS [0:FC_1_OUT_DIM-1] = {8'sd77, 8'sd-127};


`endif // MODEL_WEIGHTS_SVH
