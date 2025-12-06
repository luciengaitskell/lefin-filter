// takes signed inputs, multiplies by signed weights, sums all products + bias to produce signed outputs
module axis_fc #(
    // input layer parameters
    // expect [CH1_DATA, CH2_DATA, ..., CHn_DATA] format
    parameter integer INPUT_BIT_WIDTH = 16,
    parameter integer ELEMENTS_IN_COUNT = 8,
    localparam integer C_S00_AXIS_TDATA_WIDTH = INPUT_BIT_WIDTH * ELEMENTS_IN_COUNT,

    // output layer parameters
    // expect [OUTPUT1, OUTPUT2, ..., OUTPUTn] format
    parameter integer OUTPUT_BIT_WIDTH = 32,
    parameter integer ELEMENTS_OUT_COUNT = 2,
    localparam integer C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * ELEMENTS_OUT_COUNT,

    // fc weights and biases layer parameters
    // expect [[Out1_W1, Out1_W2, ...], [Out2_W1, Out2_W2, ...]].flatten() format for weights
    // expect [Out1_Bias, Out2_Bias, ...].flatten() format for biases
    parameter integer WEIGHT_BIT_WIDTH = 16,
    parameter integer BIAS_BIT_WIDTH = 16
)
(
    input wire aclk,
    input wire aresetn, 

    // Weights and biases
    input wire signed [WEIGHT_BIT_WIDTH-1:0] s_weights [0:ELEMENTS_OUT_COUNT-1][0:ELEMENTS_IN_COUNT-1],
    input wire signed [BIAS_BIT_WIDTH-1:0] s_biases [0:ELEMENTS_OUT_COUNT-1],

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    input wire s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [ELEMENTS_IN_COUNT-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    output logic m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [ELEMENTS_OUT_COUNT-1:0] m00_axis_tstrb

);

// inputs
logic signed [INPUT_BIT_WIDTH-1:0] inputs[0:ELEMENTS_IN_COUNT-1];
always_comb begin
    for (integer elt = 0; elt < ELEMENTS_IN_COUNT; elt++) begin
        inputs[elt] = $signed(s00_axis_tdata[INPUT_BIT_WIDTH*elt +: INPUT_BIT_WIDTH]);
    end
end

// post multiply intermediates
localparam integer POST_MULT_BIT_WIDTH = INPUT_BIT_WIDTH + WEIGHT_BIT_WIDTH;
logic signed [POST_MULT_BIT_WIDTH-1:0] post_mult_intermediates[0:ELEMENTS_OUT_COUNT-1][0:ELEMENTS_IN_COUNT-1];
always_comb begin
    for (integer out_i = 0; out_i < ELEMENTS_OUT_COUNT; out_i++) begin
        for (integer in_i = 0; in_i < ELEMENTS_IN_COUNT; in_i++) begin
            post_mult_intermediates[out_i][in_i] = 
                $signed(inputs[in_i]) * $signed(s_weights[out_i][in_i]);
        end
    end
end

// intermediates added with biases to form outputs 
logic signed [OUTPUT_BIT_WIDTH-1:0] outputs[0:ELEMENTS_OUT_COUNT-1];
always_comb begin
    for (integer out_i = 0; out_i < ELEMENTS_OUT_COUNT; out_i++) begin
        outputs[out_i] = (OUTPUT_BIT_WIDTH)'(s_biases[out_i]);
        for (integer in_i = 0; in_i < ELEMENTS_IN_COUNT; in_i++) begin
            outputs[out_i] = outputs[out_i] + (OUTPUT_BIT_WIDTH)'(post_mult_intermediates[out_i][in_i]);
        end
    end
end

// assign outputs to m00_axis_tdata
always_comb begin
    for (integer elt = 0; elt < ELEMENTS_OUT_COUNT; elt++) begin
        m00_axis_tdata[OUTPUT_BIT_WIDTH*elt +: OUTPUT_BIT_WIDTH] = outputs[elt];
    end
end

assign m00_axis_tstrb = {ELEMENTS_OUT_COUNT{1'b1}};
assign s00_axis_tready = m00_axis_tready;
assign m00_axis_tvalid = s00_axis_tvalid;
assign m00_axis_tlast  = s00_axis_tlast;
endmodule
