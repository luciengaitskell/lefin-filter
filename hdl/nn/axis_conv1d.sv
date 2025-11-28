`include "./conv1d.sv"

/*
conv1d built for an AXI4-Stream interface.

Yes, ideally it could be fully AXI4-Stream compliant,
which means we would always cache the last 24B,
using the strb to dynamically select...
but that's going to make a fairly nasty synthesis output.

We know that the xxv_eth_mac_pcs will have either a 32b
or 64b AXI4-Stream bus, and will predictably send the
ethernet packet bytes packed neatly together.

Therefore, let's build to expect the convenient number
of bytes (e.g. 4 or 8 bytes) as the inputs,
which avoids the need for the complex buffering.
*/


module axis_conv1d #(
    parameter integer C_S00_AXIS_TDATA_WIDTH = 32,
    parameter integer KERNEL_WIDTH = 25,  // FIXME: this must be larger than INPUT_WIDTH
    parameter integer STRIDE = 1,
    parameter integer INPUT_BIT_WIDTH = 8,
    parameter integer WEIGHT_BIT_WIDTH = 8,
    localparam integer INPUT_WIDTH = C_S00_AXIS_TDATA_WIDTH / INPUT_BIT_WIDTH,
    localparam integer NUM_PARALLEL_CONVS = ((INPUT_WIDTH) / STRIDE),
    localparam integer INTERMEDIATE_BIT_WIDTH = conv1d::calculate_intermediate_bit_width(
        INPUT_BIT_WIDTH, WEIGHT_BIT_WIDTH
    ),
    localparam integer OUTPUT_BIT_WIDTH = conv1d::calculate_output_bit_width(
        INTERMEDIATE_BIT_WIDTH, KERNEL_WIDTH
    ),
    localparam integer C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * NUM_PARALLEL_CONVS
) (

    input wire aclk,
    input wire aresetn,
    input wire signed [WEIGHT_BIT_WIDTH-1:0] weights[0:(KERNEL_WIDTH-1)],

    // Ports of Axi Slave Bus Interface S00_AXIS
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [INPUT_WIDTH-1:0] s00_axis_tstrb,
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [(C_M00_AXIS_TDATA_WIDTH/8)-1:0] m00_axis_tstrb
);

  initial begin
    assert (STRIDE == 1)
    else $error("Error: currently only supports STRIDE of 1, got %0d", STRIDE);
    assert (KERNEL_WIDTH > INPUT_WIDTH)
    else
      $error(
          "Error: conv1d KERNEL_WIDTH (%0d) must be larger than INPUT_WIDTH (%0d)",
          KERNEL_WIDTH,
          INPUT_WIDTH
      );
    assert ((KERNEL_WIDTH - 1) % INPUT_WIDTH == 0)
    else
      $error(
          "Error: conv1d KERNEL_WIDTH (%0d) minus 1 must be is a multiple of INPUT_WIDTH (%0d)",
          KERNEL_WIDTH,
          INPUT_WIDTH
      );
  end

  localparam integer PREVIOUS_INPUTS = KERNEL_WIDTH - 1;
  logic signed [INPUT_BIT_WIDTH-1:0] previous_inputs[0:PREVIOUS_INPUTS-1];
  localparam integer CYCLES_TO_FILL_PREVIOUS_INPUTS = (PREVIOUS_INPUTS + INPUT_WIDTH - 1) / INPUT_WIDTH;
  //  (round up division)
  logic [$clog2(CYCLES_TO_FILL_PREVIOUS_INPUTS+1)-1:0] previous_inputs_fill_cycles;
  wire previous_inputs_filled = (previous_inputs_fill_cycles == ($clog2(
      CYCLES_TO_FILL_PREVIOUS_INPUTS + 1
  ))'(CYCLES_TO_FILL_PREVIOUS_INPUTS));

  logic signed [INPUT_BIT_WIDTH-1:0] inputs[0:INPUT_WIDTH+PREVIOUS_INPUTS-1];
  always_comb begin
    for (integer i = 0; i < INPUT_WIDTH; i++) begin
      inputs[i+(KERNEL_WIDTH-1)] = s00_axis_tdata[INPUT_BIT_WIDTH*i+:INPUT_BIT_WIDTH];
    end
    for (integer i = 0; i < (KERNEL_WIDTH - 1); i++) begin
      inputs[i] = previous_inputs[i];
    end
  end

  logic signed [OUTPUT_BIT_WIDTH-1:0] activations[0:NUM_PARALLEL_CONVS-1];

  generate
    for (genvar i = 0; i < NUM_PARALLEL_CONVS; i++) begin : parallel_convs
      conv1d_layer #(
          .INPUT_BIT_WIDTH(INPUT_BIT_WIDTH),
          .WEIGHT_BIT_WIDTH(WEIGHT_BIT_WIDTH),
          .KERNEL_WIDTH(KERNEL_WIDTH),
          .STAGE_1_MULT(COMBINATIONAL),
          .STAGE_2_ADD(COMBINATIONAL)
      ) conv1d_parallel (
          .clk             (aclk),
          .inputs          (inputs[i+:KERNEL_WIDTH]),
          .inputs_valid    (s00_axis_tvalid && previous_inputs_filled),
          // was considerign `&& m00_axis_tready` but I think it's wrong
          .weights         (weights),
          .activation      (activations[i]),
          .activation_valid(m00_axis_tstrb[i])
      );
    end
  endgenerate

  localparam integer RETAINED_PREVIOUS_INPUTS = (PREVIOUS_INPUTS) - INPUT_WIDTH;
  always_ff @(posedge aclk) begin
    if (!aresetn) begin
      previous_inputs_fill_cycles <= '0;
    end else begin
      if (s00_axis_tvalid && m00_axis_tready && !previous_inputs_filled) begin
        previous_inputs_fill_cycles <= previous_inputs_fill_cycles + 1;
      end
      if ((m00_axis_tvalid && m00_axis_tready) || !previous_inputs_filled) begin
        for (integer i = 0; i < RETAINED_PREVIOUS_INPUTS; i++) begin
          previous_inputs[i] <= previous_inputs[i+INPUT_WIDTH];
        end
        for (integer i = RETAINED_PREVIOUS_INPUTS; i < PREVIOUS_INPUTS; i++) begin
          previous_inputs[i] <= inputs[i+PREVIOUS_INPUTS-RETAINED_PREVIOUS_INPUTS];
        end
      end
    end
  end

  assign s00_axis_tready = m00_axis_tready || !previous_inputs_filled;

  always_comb begin
    m00_axis_tdata = '0;
    for (integer i = 0; i < NUM_PARALLEL_CONVS; i++) begin
      m00_axis_tdata[OUTPUT_BIT_WIDTH*i+:OUTPUT_BIT_WIDTH] = activations[i];
    end
    m00_axis_tvalid = m00_axis_tstrb[0];
    m00_axis_tlast  = s00_axis_tlast; // FIXME: this is only correct for KERNEL_WIDTH == INPUT_WIDTH + 1
  end


endmodule
