module lefin_filter #(
    parameter int C_S00_AXIS_TDATA_WIDTH = 32,
    parameter int BIT_WIDTH = 8,
    localparam int WIDTH = C_S00_AXIS_TDATA_WIDTH / BIT_WIDTH,
    localparam int C_M00_AXIS_TDATA_WIDTH = C_S00_AXIS_TDATA_WIDTH
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
    output logic [WIDTH-1:0] m00_axis_tkeep
);

  logic axis_fifo_s00_axis_tready;
  logic model_classification_valid;
  logic model_classification_malware;
  axis_fifo #(
      .DATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .DEPTH     (1500),
      .STRB_WIDTH(WIDTH),
      .KEEP_WIDTH(WIDTH)
  ) axis_fifo (
      .aclk              (aclk),
      .aresetn           (aresetn),
      .s00_axis_tdata    (s00_axis_tdata),
      /* verilator lint_off PINCONNECTEMPTY */
      .s00_axis_tstrb    (),
      /* verilator lint_on PINCONNECTEMPTY */
      .s00_axis_tkeep    (s00_axis_tkeep),
      .s00_axis_tvalid   (s00_axis_tvalid),
      .s00_axis_tlast    (s00_axis_tlast),
      .s00_axis_tready   (axis_fifo_s00_axis_tready),
      .m00_axis_tdata    (m00_axis_tdata),
      /* verilator lint_off PINCONNECTEMPTY */
      .m00_axis_tstrb    (),
      /* verilator lint_on PINCONNECTEMPTY */
      .m00_axis_tkeep    (m00_axis_tkeep),
      .m00_axis_tvalid   (m00_axis_tvalid),
      .m00_axis_tlast    (m00_axis_tlast),
      .m00_axis_tready   (m00_axis_tready),
      .packet_input_valid(model_classification_valid),
      .packet_input_good (!model_classification_malware)
  );

  logic classifier_s00_axis_tready;
  classifier #(
    .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
    .BIT_WIDTH             (BIT_WIDTH)
   ) classifier (
    .aclk                        (aclk),
    .aresetn                     (aresetn),
    .s00_axis_tlast              (s00_axis_tlast),
    .s00_axis_tvalid             (s00_axis_tvalid),
    .s00_axis_tdata              (s00_axis_tdata),
    .s00_axis_tkeep              (s00_axis_tkeep),
    .s00_axis_tready             (classifier_s00_axis_tready),
    .model_classification_valid  (model_classification_valid),
    .model_classification_malware(model_classification_malware)
  );

  assign s00_axis_tready = axis_fifo_s00_axis_tready && classifier_s00_axis_tready;

endmodule
