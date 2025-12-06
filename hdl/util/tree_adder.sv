// A signed adder that sums NUM_INPUTS inputs of INPUT_BIT_WIDTH bits each
// The output sum is OUTPUT_BIT_WIDTH bits wide to prevent overflow
module tree_adder #(
    parameter integer INPUT_BIT_WIDTH = 16,
    parameter integer NUM_INPUTS = 4,
    localparam integer OUTPUT_BIT_WIDTH = INPUT_BIT_WIDTH + $clog2(NUM_INPUTS)
)
(
    input wire signed [INPUT_BIT_WIDTH-1:0] inputs[0:NUM_INPUTS-1],
    output logic signed [OUTPUT_BIT_WIDTH-1:0] sum
);

// To be replaced with a more efficient tree adder structure if needed
// DISPLAY INPUTS
initial begin
    $display("Tree Adder instantiated with %0d inputs of %0d bits each, producing %0d bit output",
        NUM_INPUTS, INPUT_BIT_WIDTH, OUTPUT_BIT_WIDTH);
    $display("Inputs: %p", inputs);
end
always_comb begin
    integer i;
    sum = '0;
    for (i = 0; i < NUM_INPUTS; i++) begin
        sum = sum + (OUTPUT_BIT_WIDTH)'(inputs[i]);
    end
end

endmodule
