## QSFP

#set_property PACKAGE_PIN AL22 [ get_ports "QSFP_MODPRSL" ]
#set_property PACKAGE_PIN AM22 [ get_ports "QSFP_INTL" ]
#set_property PACKAGE_PIN AL21 [ get_ports "QSFP_RESETL" ]
#set_property PACKAGE_PIN AN22 [ get_ports "QSFP_LPMODE" ]
#set_property PACKAGE_PIN AK22 [ get_ports "QSFP_MODSEL" ]
#set_property IOSTANDARD LVCMOS18 [ get_ports "QSFP*"]

# GTY_128_REF_CLK_QSFP_P
set_property PACKAGE_PIN AA33 [ get_ports "gt_ref_clk_clk_p" ]
# GTY_128_REF_CLK_QSFP_N
set_property PACKAGE_PIN AA34 [ get_ports "gt_ref_clk_clk_n" ]

set_property BITSTREAM.CONFIG.UNUSEDPIN PULLUP [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
