//Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
//Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2025.1 (lin64) Build 6140274 Wed May 21 22:58:25 MDT 2025
//Date        : Mon Dec  8 14:37:32 2025
//Host        : grater running 64-bit Ubuntu 25.04
//Command     : generate_target design_1_wrapper.bd
//Design      : design_1_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module design_1_wrapper
   (gt_ref_clk_clk_n,
    gt_ref_clk_clk_p,
    gt_rtl_grx_n,
    gt_rtl_grx_p,
    gt_rtl_gtx_n,
    gt_rtl_gtx_p);
  input gt_ref_clk_clk_n;
  input gt_ref_clk_clk_p;
  input [1:0]gt_rtl_grx_n;
  input [1:0]gt_rtl_grx_p;
  output [1:0]gt_rtl_gtx_n;
  output [1:0]gt_rtl_gtx_p;

  wire gt_ref_clk_clk_n;
  wire gt_ref_clk_clk_p;
  wire [1:0]gt_rtl_grx_n;
  wire [1:0]gt_rtl_grx_p;
  wire [1:0]gt_rtl_gtx_n;
  wire [1:0]gt_rtl_gtx_p;

  design_1 design_1_i
       (.gt_ref_clk_clk_n(gt_ref_clk_clk_n),
        .gt_ref_clk_clk_p(gt_ref_clk_clk_p),
        .gt_rtl_grx_n(gt_rtl_grx_n),
        .gt_rtl_grx_p(gt_rtl_grx_p),
        .gt_rtl_gtx_n(gt_rtl_gtx_n),
        .gt_rtl_gtx_p(gt_rtl_gtx_p));
endmodule
