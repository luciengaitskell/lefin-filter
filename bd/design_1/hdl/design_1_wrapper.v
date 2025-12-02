//Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
//Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2025.1 (lin64) Build 6140274 Wed May 21 22:58:25 MDT 2025
//Date        : Tue Dec  2 18:21:47 2025
//Host        : grater running 64-bit Ubuntu 25.04
//Command     : generate_target design_1_wrapper.bd
//Design      : design_1_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module design_1_wrapper
   (diff_clock_rtl_clk_n,
    diff_clock_rtl_clk_p,
    gt_rtl_grx_n,
    gt_rtl_grx_p,
    gt_rtl_gtx_n,
    gt_rtl_gtx_p,
    led);
  input diff_clock_rtl_clk_n;
  input diff_clock_rtl_clk_p;
  input [1:0]gt_rtl_grx_n;
  input [1:0]gt_rtl_grx_p;
  output [1:0]gt_rtl_gtx_n;
  output [1:0]gt_rtl_gtx_p;
  output led;

  wire diff_clock_rtl_clk_n;
  wire diff_clock_rtl_clk_p;
  wire [1:0]gt_rtl_grx_n;
  wire [1:0]gt_rtl_grx_p;
  wire [1:0]gt_rtl_gtx_n;
  wire [1:0]gt_rtl_gtx_p;
  wire led;

  design_1 design_1_i
       (.diff_clock_rtl_clk_n(diff_clock_rtl_clk_n),
        .diff_clock_rtl_clk_p(diff_clock_rtl_clk_p),
        .gt_rtl_grx_n(gt_rtl_grx_n),
        .gt_rtl_grx_p(gt_rtl_grx_p),
        .gt_rtl_gtx_n(gt_rtl_gtx_n),
        .gt_rtl_gtx_p(gt_rtl_gtx_p),
        .led(led));
endmodule
