
module model_interface #(
    parameter int C_S00_AXIS_TDATA_WIDTH = 32,
    parameter int BIT_WIDTH = 8,
    localparam int WIDTH = C_S00_AXIS_TDATA_WIDTH / BIT_WIDTH,
    localparam int C_M00_AXIS_TDATA_WIDTH = C_S00_AXIS_TDATA_WIDTH,
    parameter int MAXIMUM_INPUT_BYTES = 768
) (
    input wire aclk,
    input wire aresetn,

    // Ports of Axi Slave Bus Interface S00_AXIS
    //  from the Ethernet Subsystem IP
    input wire s00_axis_tlast,
    s00_axis_tvalid,
    input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
    input wire [WIDTH-1:0] s00_axis_tkeep,  // IP uses tkeep
    output logic s00_axis_tready,

    // Ports of Axi Master Bus Interface M00_AXIS
    input wire m00_axis_tready,
    output logic m00_axis_tvalid,
    m00_axis_tlast,
    output logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
    output logic [WIDTH-1:0] m00_axis_tstrb
    // we use tstrb in the pipeline as invalid bytes are still retain positional meaning
);

  localparam int MAXIMUM_CYCLES = MAXIMUM_INPUT_BYTES / WIDTH;
  initial begin
    assert (MAXIMUM_CYCLES * WIDTH == MAXIMUM_INPUT_BYTES)
    else
      $error(
          "Error: MAXIMUM_INPUT_BYTES (%0d) must be a multiple of WIDTH (%0d)",
          MAXIMUM_INPUT_BYTES,
          WIDTH
      );
  end

  wire s00_axis_transacted = s00_axis_tvalid && s00_axis_tready;

  logic [$clog2(MAXIMUM_CYCLES+1)-1:0] s00_axis_transaction_count;
  wire waiting_for_s00_axis_finish = (s00_axis_transaction_count == ($clog2(
      MAXIMUM_CYCLES + 1
  ))'(MAXIMUM_CYCLES));
  counter #(
      .MAXIMUM  (MAXIMUM_CYCLES+1),
      .ROLL_OVER(0)
  ) s00_axis_transaction_counter (
      .clk    (aclk),
      .rst    (!aresetn || (s00_axis_tlast && s00_axis_transacted)),
      .trigger(s00_axis_transacted && !waiting_for_s00_axis_finish),
      .count  (s00_axis_transaction_count)
  );

  assign s00_axis_tready = m00_axis_tready || waiting_for_s00_axis_finish;
  assign m00_axis_tvalid = s00_axis_tvalid && !waiting_for_s00_axis_finish;
  assign m00_axis_tdata  = s00_axis_tdata;
  assign m00_axis_tstrb  = s00_axis_tkeep;


  // FIXME: need to handle the m00_axis_tlast??
endmodule
