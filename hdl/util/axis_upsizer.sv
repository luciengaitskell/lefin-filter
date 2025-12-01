module axis_conv1d #(
    parameter int BIT_WIDTH = 8,
    parameter int C_S00_AXIS_TDATA_WIDTH = 32,
    localparam int INPUT_WIDTH = C_S00_AXIS_TDATA_WIDTH / BIT_WIDTH,
    parameter int C_M00_AXIS_TDATA_WIDTH = 64,
    localparam int OUTPUT_WIDTH = C_M00_AXIS_TDATA_WIDTH / BIT_WIDTH
) (
    input wire aclk,
    input wire aresetn,

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
    output logic [OUTPUT_WIDTH-1:0] m00_axis_tstrb
);

  initial begin
    assert (C_M00_AXIS_TDATA_WIDTH > C_S00_AXIS_TDATA_WIDTH)
    else
      $error(
          "Error: conv1d upsizer output width (%0d) must be larger than input width (%0d)",
          C_M00_AXIS_TDATA_WIDTH,
          C_S00_AXIS_TDATA_WIDTH
      );
  end

  logic [BIT_WIDTH-1:0] previous_inputs[0:OUTPUT_WIDTH-1];
  localparam int PREVIOUS_INPUT_CW = $clog2(OUTPUT_WIDTH);
  logic [PREVIOUS_INPUT_CW-1:0] previous_inputs_count;

  always_ff @(posedge aclk) begin
    if (!aresetn) begin
      previous_inputs_count <= '0;
    end else begin
      if (s00_axis_tvalid) begin
        if (m00_axis_tready) begin
          if (previous_inputs_count >= (PREVIOUS_INPUT_CW)'(OUTPUT_WIDTH - INPUT_WIDTH)) begin
            previous_inputs_count <= previous_inputs_count - (PREVIOUS_INPUT_CW)'(OUTPUT_WIDTH - INPUT_WIDTH);
            // send as much data from the previous inputs buffer as possible
            // cache the rest of the new inputs

          end else begin
            // not enough previous inputs to send out full output
          end

        end
      end
    end
  end

  assign s00_axis_tready = m00_axis_tready || (previous_inputs_count <= (PREVIOUS_INPUT_CW)'(OUTPUT_WIDTH - INPUT_WIDTH));


endmodule
