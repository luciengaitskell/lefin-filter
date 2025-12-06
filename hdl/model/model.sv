`include "weights.svh"

module model #(
    parameter int C_S00_AXIS_TDATA_WIDTH = 32,
    parameter int INPUT_BIT_WIDTH = 8,
    localparam int INPUT_WIDTH = C_S00_AXIS_TDATA_WIDTH / INPUT_BIT_WIDTH,
    localparam OUTPUT_BIT_WIDTH = 32,  // FIXME: be smarter about this??
    parameter int C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * FC_1_OUT_DIM
) (
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

  localparam int CONV1D_1_INTERMEDIATE_BIT_WIDTH = conv1d_pkg::calculate_intermediate_bit_width(
      INPUT_BIT_WIDTH, CONV1D_1_WEIGHT_BIT_WIDTH
  );
  localparam int CONV1D_1_OUTPUT_BIT_WIDTH = conv1d_pkg::calculate_output_bit_width(
      CONV1D_1_INTERMEDIATE_BIT_WIDTH, CONV1D_1_KERNEL_WIDTH
  );
  localparam int CONV1D_1_NUM_PARALLEL_CONVS = ((INPUT_WIDTH) / CONV1D_1_STRIDE);
  localparam int CONV1D_1_C_M00_AXIS_TDATA_WIDTH = CONV1D_1_OUTPUT_BIT_WIDTH * CONV1D_1_NUM_PARALLEL_CONVS * CONV1D_1_CHANNEL_OUT_COUNT;
  logic [CONV1D_1_C_M00_AXIS_TDATA_WIDTH-1 : 0] conv1d_m00_axis_tdata;
  logic [(CONV1D_1_C_M00_AXIS_TDATA_WIDTH/INPUT_BIT_WIDTH)-1:0] conv1d_m00_axis_tstrb;
  logic conv1d_m00_axis_tvalid;
  logic conv1d_m00_axis_tlast;
  logic conv1d_m00_axis_tready;
  axis_conv1d #(
      .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
      .KERNEL_WIDTH          (CONV1D_1_KERNEL_WIDTH),
      .CHANNEL_OUT_COUNT     (CONV1D_1_CHANNEL_OUT_COUNT),
      .STRIDE                (CONV1D_1_STRIDE),
      .INPUT_BIT_WIDTH       (INPUT_BIT_WIDTH),
      .WEIGHT_BIT_WIDTH      (CONV1D_1_WEIGHT_BIT_WIDTH)
  ) axis_conv1d (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .weights        (CONV1D_1_WEIGHT),
      .biases         (CONV1D_1_BIAS),
      .s00_axis_tlast (s00_axis_tlast),
      .s00_axis_tvalid(s00_axis_tvalid),
      .s00_axis_tdata (s00_axis_tdata),
      .s00_axis_tstrb (s00_axis_tstrb),
      .s00_axis_tready(s00_axis_tready),
      .m00_axis_tready(conv1d_m00_axis_tready),
      .m00_axis_tvalid(conv1d_m00_axis_tvalid),
      .m00_axis_tlast (conv1d_m00_axis_tlast),
      .m00_axis_tdata (conv1d_m00_axis_tdata),
      .m00_axis_tstrb (conv1d_m00_axis_tstrb)
  );


  localparam int GMP_C_M00_AXIS_TDATA_WIDTH = CONV1D_1_OUTPUT_BIT_WIDTH * CONV1D_1_CHANNEL_OUT_COUNT;
  localparam int GMP_WIDTH = CONV1D_1_NUM_PARALLEL_CONVS;
  localparam int GMP_BIT_WIDTH = CONV1D_1_OUTPUT_BIT_WIDTH;
  logic [GMP_C_M00_AXIS_TDATA_WIDTH-1 : 0] gmp_m00_axis_tdata;
  logic [(GMP_C_M00_AXIS_TDATA_WIDTH/CONV1D_1_OUTPUT_BIT_WIDTH)-1:0] gmp_m00_axis_tstrb;
  logic gmp_m00_axis_tvalid;
  logic gmp_m00_axis_tlast;
  logic gmp_m00_axis_tready;
  axis_gmp #(
      .WIDTH(GMP_WIDTH),
      .BIT_WIDTH(GMP_BIT_WIDTH),
      .CHANNEL_COUNT(CONV1D_1_CHANNEL_OUT_COUNT)
  ) axis_gmp (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .s00_axis_tlast (conv1d_m00_axis_tlast),
      .s00_axis_tvalid(conv1d_m00_axis_tvalid),
      .s00_axis_tdata (conv1d_m00_axis_tdata),
      .s00_axis_tstrb (conv1d_m00_axis_tstrb),
      .s00_axis_tready(conv1d_m00_axis_tready),
      .m00_axis_tready(gmp_m00_axis_tready),
      .m00_axis_tvalid(gmp_m00_axis_tvalid),
      .m00_axis_tlast (gmp_m00_axis_tlast),
      .m00_axis_tdata (gmp_m00_axis_tdata),
      .m00_axis_tstrb (gmp_m00_axis_tstrb)
  );


  axis_fc #(
      .INPUT_BIT_WIDTH(GMP_BIT_WIDTH),
      .ELEMENTS_IN_COUNT(FC_1_IN_DIM),
      .OUTPUT_BIT_WIDTH(OUTPUT_BIT_WIDTH),
      .ELEMENTS_OUT_COUNT(FC_1_OUT_DIM),
      .WEIGHT_BIT_WIDTH(FC_1_WEIGHT_BIT_WIDTH),
      .BIAS_BIT_WIDTH(FC_1_BIAS_BIT_WIDTH)
  ) axis_fc (
      .aclk           (aclk),
      .aresetn        (aresetn),
      .s_weights      (FC_1_WEIGHT),
      .s_biases       (FC_1_BIAS),
      .s00_axis_tlast (gmp_m00_axis_tlast),
      .s00_axis_tvalid(gmp_m00_axis_tvalid),
      .s00_axis_tdata (gmp_m00_axis_tdata),
      .s00_axis_tstrb (gmp_m00_axis_tstrb),
      .s00_axis_tready(gmp_m00_axis_tready),
      .m00_axis_tready(m00_axis_tready),
      .m00_axis_tvalid(m00_axis_tvalid),
      .m00_axis_tlast (m00_axis_tlast),
      .m00_axis_tdata (m00_axis_tdata),
      .m00_axis_tstrb (m00_axis_tstrb)
  );

endmodule
