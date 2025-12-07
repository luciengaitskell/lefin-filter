
/* verilator lint_off DECLFILENAME */
package conv1d_pkg;
  function automatic int calculate_intermediate_bit_width(int input_bit_width,
                                                          int weight_bit_width);
    return input_bit_width + weight_bit_width;
  endfunction
  function automatic int calculate_output_bit_width(int intermediate_bit_width, int kernel_width);
    return intermediate_bit_width + $clog2(kernel_width + 1);  // +1 for bias
  endfunction
endpackage
/* verilator lint_on DECLFILENAME */

module conv1d #(
    parameter integer INPUT_BIT_WIDTH = 8,
    parameter integer WEIGHT_BIT_WIDTH = 8,
    parameter integer KERNEL_WIDTH = 3,
    parameter integer CHANNEL_IN_COUNT = 1,
    parameter integer CHANNEL_OUT_COUNT = 1,
    localparam integer INTERMEDIATE_BIT_WIDTH = conv1d_pkg::calculate_intermediate_bit_width(
        INPUT_BIT_WIDTH, WEIGHT_BIT_WIDTH
    ),
    localparam integer OUTPUT_BIT_WIDTH = conv1d_pkg::calculate_output_bit_width(
        INTERMEDIATE_BIT_WIDTH, KERNEL_WIDTH
    ),
    parameter connector_pkg::logic_style STAGE_1_MULT = connector_pkg::COMBINATIONAL,
    parameter connector_pkg::logic_style STAGE_2_ADD = connector_pkg::COMBINATIONAL
) (
    input wire clk,
    input wire signed [INPUT_BIT_WIDTH-1:0] inputs[0:KERNEL_WIDTH-1],
    input wire inputs_valid,
    input wire signed [WEIGHT_BIT_WIDTH-1:0] weights[0:CHANNEL_OUT_COUNT-1][0:CHANNEL_IN_COUNT-1][0:KERNEL_WIDTH-1],
    input wire signed [WEIGHT_BIT_WIDTH-1:0] biases[0:CHANNEL_OUT_COUNT-1],
    output logic signed [OUTPUT_BIT_WIDTH-1:0] activation[0:CHANNEL_OUT_COUNT-1],
    output logic activation_valid
);

  initial begin
    assert (CHANNEL_IN_COUNT == 1)
    else $error("Error: currently only supports CHANNEL_IN_COUNT of 1, got %0d", CHANNEL_IN_COUNT);
  end

  logic signed [INTERMEDIATE_BIT_WIDTH-1 : 0] intermediates[0:CHANNEL_OUT_COUNT-1][0:KERNEL_WIDTH-1];

  logic [CHANNEL_OUT_COUNT-1:0][KERNEL_WIDTH-1:0] stage_1_valid;

  logic signed [OUTPUT_BIT_WIDTH-1:0] adder_steps[0:CHANNEL_OUT_COUNT-1][0:KERNEL_WIDTH-1];

  logic [CHANNEL_OUT_COUNT-1:0] stage_2_valid;

  always_comb begin
    for (integer channel_out = 0; channel_out < CHANNEL_OUT_COUNT; channel_out++) begin
      adder_steps[channel_out][0] = OUTPUT_BIT_WIDTH'(biases[channel_out]) + OUTPUT_BIT_WIDTH'(intermediates[channel_out][0]);
      for (integer i = 1; i < KERNEL_WIDTH; i++) begin
        adder_steps[channel_out][i] = adder_steps[channel_out][i-1] + OUTPUT_BIT_WIDTH'(intermediates[channel_out][i]);
      end
    end
  end

  generate
    for (
        genvar channel_out = 0; channel_out < CHANNEL_OUT_COUNT; channel_out++
    ) begin : stage_1_channel_out
      for (genvar i = 0; i < KERNEL_WIDTH; i++) begin : stage_1_multi_connector
        connector #(
            .connectivity(STAGE_1_MULT),
            .WIDTH       (INTERMEDIATE_BIT_WIDTH)
        ) stage_1_multi_connector (
            .clk(clk),
            .in(INTERMEDIATE_BIT_WIDTH'(inputs[i]) * INTERMEDIATE_BIT_WIDTH'(weights[channel_out][0][i])),
            .in_valid(inputs_valid),
            .out(intermediates[channel_out][i]),
            .out_valid(stage_1_valid[channel_out][i])
        );
      end

      connector #(
          .connectivity(STAGE_2_ADD),
          .WIDTH       (OUTPUT_BIT_WIDTH)
      ) connector (
          .clk(clk),
          .in(adder_steps[channel_out][KERNEL_WIDTH-1]),
          .in_valid(&stage_1_valid[channel_out]),
          .out(activation[channel_out]),
          .out_valid(stage_2_valid[channel_out])
      );
    end
  endgenerate

  assign activation_valid = &stage_2_valid;
endmodule
