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
    parameter integer BIAS_BIT_WIDTH = 16,
    localparam integer NUM_WEIGHTS = CHANNEL_IN_COUNT * CHANNEL_OUT_COUNT,
    localparam integer NUM_BIASES = CHANNEL_OUT_COUNT
)
(
    input wire aclk,
    input wire aresetn, 

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    input wire s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [CHANNEL_IN_COUNT-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    output logic m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [CHANNEL_OUT_COUNT-1:0] m00_axis_tstrb
);

//weights
logic signed [WEIGHT_BIT_WIDTH-1:0] weights[0:ELEMENTS_OUT_COUNT-1][0:ELEMENTS_IN_COUNT-1];
always_comb begin
    for (integer out_i = 0; out_i < ELEMENTS_OUT_COUNT; out_i++) begin
        for (integer in_i = 0; in_i < ELEMENTS_IN_COUNT; in_i++) begin
            weights[out_i][in_i] = $signed(s00_axis_tdata[WEIGHT_BIT_WIDTH*(out_i*ELEMENTS_IN_COUNT + in_i) +: WEIGHT_BIT_WIDTH]);
        end
    end
end

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
                INPUT_BIT_WIDTH'(inputs[in_i]) * $signed(WEIGHT_BIT_WIDTH'(weights[out_i][in_i]));
        end
    end
end

// intermediates added with biases to form outputs 
logic signed [OUTPUT_BIT_WIDTH-1:0] outputs[0:ELEMENTS_OUT_COUNT-1];
generate
    for (genvar out_i = 0; out_i < ELEMENTS_OUT_COUNT; out_i++) begin : gen_adder_per_output
        tree_adder #(
            .INPUT_BIT_WIDTH (POST_MULT_BIT_WIDTH),
            .NUM_INPUTS      (ELEMENTS_IN_COUNT),
            .BIAS_BIT_WIDTH  (BIAS_BIT_WIDTH),
            .OUTPUT_BIT_WIDTH(OUTPUT_BIT_WIDTH)
        ) adder (
            .inputs  (post_mult_intermediates[out_i]),
            .sum     (outputs[out_i])
        );
    end
endgenerate

// assign outputs to m00_axis_tdata
always_comb begin
    for (integer elt = 0; elt < ELEMENTS_OUT_COUNT; elt++) begin
        m00_axis_tdata[OUTPUT_BIT_WIDTH*elt +: OUTPUT_BIT_WIDTH] = outputs[elt] + $signed(BIAS_BIT_WIDTH'(biases[elt]));
    end
end

assign m00_axis_tstrb = {CHANNEL_OUT_COUNT{1'b1}};
assign s00_axis_tready = m00_axis_tready;
assign m00_axis_tvalid = s00_axis_tvalid;
assign m00_axis_tlast  = s00_axis_tlast;

// add all intermediates with their biases to get final outputs using tree adder
localparam integer ADDER_STAGES = $clog2(ELEMENTS_IN_COUNT + 1); // +1 for bias
// top of tree is index 0
logic signed [OUTPUT_BIT_WIDTH-1:0] adder_tree[0:ELEMENTS_OUT_COUNT-1][0:ADDER_STAGES-1][0:(1 << ADDER_STAGES)-1];
always_comb begin
    // for each output element
    for (integer out_i = 0; out_i < ELEMENTS_OUT_COUNT; out_i++) begin
        // stage 0 is inputs + bias
        adder_tree[out_i][0][0] = 

endmodule