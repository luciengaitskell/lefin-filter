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
  logic model_classification;
  axis_fifo #(
      .DATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .DEPTH     (1500),
      .STRB_WIDTH(WIDTH),
      .KEEP_WIDTH(WIDTH)
  ) axis_fifo (
      .aclk              (aclk),
      .aresetn           (aresetn),
      .s00_axis_tdata    (s00_axis_tdata),
      .s00_axis_tstrb    (),
      .s00_axis_tkeep    (s00_axis_tkeep),
      .s00_axis_tvalid   (s00_axis_tvalid),
      .s00_axis_tlast    (s00_axis_tlast),
      .s00_axis_tready   (axis_fifo_s00_axis_tready),
      .m00_axis_tdata    (m00_axis_tdata),
      .m00_axis_tstrb    (),
      .m00_axis_tkeep    (m00_axis_tkeep),
      .m00_axis_tvalid   (m00_axis_tvalid),
      .m00_axis_tlast    (m00_axis_tlast),
      .m00_axis_tready   (m00_axis_tready),
      .packet_input_valid(1'b1),
      .packet_input_good (1'b1)
  );

  logic model_interface_s00_axis_tready;
  logic model_interface_m00_axis_tvalid;
  logic model_interface_m00_axis_tlast;
  logic [C_M00_AXIS_TDATA_WIDTH-1 : 0] model_interface_m00_axis_tdata;
  logic [WIDTH-1:0] model_interface_m00_axis_tstrb;
  logic model_interface_m00_axis_tready;
  model_interface #(
      .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .BIT_WIDTH             (BIT_WIDTH)
  ) model_interface (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .s00_axis_tlast (s00_axis_tlast),
      .s00_axis_tvalid(s00_axis_tvalid),
      .s00_axis_tdata (s00_axis_tdata),
      .s00_axis_tkeep (s00_axis_tkeep),
      .s00_axis_tready(model_interface_s00_axis_tready),
      .m00_axis_tready(model_interface_m00_axis_tready),
      .m00_axis_tvalid(model_interface_m00_axis_tvalid),
      .m00_axis_tlast (model_interface_m00_axis_tlast),
      .m00_axis_tdata (model_interface_m00_axis_tdata),
      .m00_axis_tstrb (model_interface_m00_axis_tstrb)
  );
  assign s00_axis_tready = axis_fifo_s00_axis_tready && model_interface_s00_axis_tready;

  localparam int SIGNED_OUTPUT_BIT_WIDTH = BIT_WIDTH + 1;
  localparam int CONV1D_1_INTERMEDIATE_BIT_WIDTH = conv1d_pkg::calculate_intermediate_bit_width(
      SIGNED_OUTPUT_BIT_WIDTH, model_params::CONV1D_1_WEIGHT_BIT_WIDTH
  );
  localparam int CONV1D_1_OUTPUT_BIT_WIDTH = conv1d_pkg::calculate_output_bit_width(
      CONV1D_1_INTERMEDIATE_BIT_WIDTH, model_params::CONV1D_1_KERNEL_WIDTH
  );
  localparam int GMP_BIT_WIDTH = CONV1D_1_OUTPUT_BIT_WIDTH;
  localparam int MODEL_OUTPUT_BIT_WIDTH = (GMP_BIT_WIDTH + model_params::FC_WEIGHT_BIT_WIDTH) + $clog2(
      model_params::FC_IN_DIM + 1
  );
  localparam int MODEL_C_M00_AXIS_TDATA_WIDTH = MODEL_OUTPUT_BIT_WIDTH * model_params::FC_OUT_DIM;
  logic model_m00_axis_tready;
  logic model_m00_axis_tvalid;
  logic model_m00_axis_tlast;
  logic [MODEL_C_M00_AXIS_TDATA_WIDTH-1 : 0] model_m00_axis_tdata;
  logic [(MODEL_C_M00_AXIS_TDATA_WIDTH/MODEL_OUTPUT_BIT_WIDTH)-1:0] model_m00_axis_tstrb;
  model #(
      .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .INPUT_BIT_WIDTH       (BIT_WIDTH)
  ) model (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .s00_axis_tlast (model_interface_m00_axis_tlast),
      .s00_axis_tvalid(model_interface_m00_axis_tvalid),
      .s00_axis_tdata (model_interface_m00_axis_tdata),
      .s00_axis_tstrb (model_interface_m00_axis_tstrb),
      .s00_axis_tready(model_interface_m00_axis_tready),
      .m00_axis_tready(model_m00_axis_tready),
      .m00_axis_tvalid(model_m00_axis_tvalid),
      .m00_axis_tlast (model_m00_axis_tlast),
      .m00_axis_tdata (model_m00_axis_tdata),
      .m00_axis_tstrb (model_m00_axis_tstrb)
  );

  axis_comparator #(
      .DATA_WIDTH(MODEL_OUTPUT_BIT_WIDTH)
  ) axis_comparator (
      .aclk            (aclk),
      .aresetn         (aresetn),
      .s00_axis_tvalid (model_m00_axis_tvalid),
      .s00_axis_tdata  (model_m00_axis_tdata),
      .s00_axis_tstrb  (model_m00_axis_tstrb),
      .s00_axis_tlast  (model_m00_axis_tlast),
      .s00_axis_tready (model_m00_axis_tready),
      .output_valid    (model_classification_valid),
      .top_half_greater(model_classification)
  );
endmodule
