`include "../util/connector.sv"

module conv1d #(
    parameter integer INPUT_BIT_WIDTH = 8,
    parameter integer WEIGHT_BIT_WIDTH = 8,
    parameter integer KERNEL_WIDTH = 3,
    localparam integer INTERMEDIATE_BIT_WIDTH = INPUT_BIT_WIDTH + WEIGHT_BIT_WIDTH,
    localparam integer OUTPUT_BIT_WIDTH = INTERMEDIATE_BIT_WIDTH + $clog2(KERNEL_WIDTH),
    parameter logic_style STAGE_1_MULT = COMBINATIONAL,
    parameter logic_style STAGE_2_ADD = COMBINATIONAL
) (
    input wire clk,
    input wire signed [INPUT_BIT_WIDTH-1:0] inputs[0:KERNEL_WIDTH-1],
    input wire inputs_valid,
    input wire signed [WEIGHT_BIT_WIDTH-1:0] weights[0:KERNEL_WIDTH-1],
    output logic signed [OUTPUT_BIT_WIDTH-1:0] activation,
    output logic activation_valid
);

  logic signed [INTERMEDIATE_BIT_WIDTH-1 : 0] intermediates[0:KERNEL_WIDTH-1];

  logic [KERNEL_WIDTH-1:0] stage_1_valid;

  generate
    for (genvar i = 0; i < KERNEL_WIDTH; i++) begin : stage_1_multi_connector
      connector #(
          .connectivity(STAGE_1_MULT),
          .WIDTH       (INTERMEDIATE_BIT_WIDTH)
      ) stage_1_multi_connector (
          .clk(clk),
          .in(INTERMEDIATE_BIT_WIDTH'(inputs[i]) * INTERMEDIATE_BIT_WIDTH'(weights[i])),
          .in_valid(inputs_valid),
          .out(intermediates[i]),
          .out_valid(stage_1_valid[i])
      );
    end
  endgenerate

  logic signed [OUTPUT_BIT_WIDTH-1:0] adder_steps[0:KERNEL_WIDTH-1];

  always_comb begin
    adder_steps[0] = OUTPUT_BIT_WIDTH'(intermediates[0]);
    for (integer i = 1; i < KERNEL_WIDTH; i++) begin
      adder_steps[i] = adder_steps[i-1] + OUTPUT_BIT_WIDTH'(intermediates[i]);
    end
  end

  connector #(
      .connectivity(STAGE_2_ADD),
      .WIDTH       (OUTPUT_BIT_WIDTH)
  ) connector (
      .clk(clk),
      .in(adder_steps[KERNEL_WIDTH-1]),
      .in_valid(&stage_1_valid),
      .out(activation),
      .out_valid(activation_valid)
  );
endmodule
