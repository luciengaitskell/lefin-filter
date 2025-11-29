
`timescale 1 ns / 1 ps

	module model_demo #
	(
		// Users to add parameters here

		// User parameters ends
		// Do not modify the parameters beyond this line


		// Parameters of Axi Slave Bus Interface S00_AXIS
		parameter integer C_S00_AXIS_TDATA_WIDTH	= 64
	)
	(
		// Users to add ports here
        output wire classification,
		// User ports ends
		// Do not modify the ports beyond this line


		// Ports of Axi Slave Bus Interface S00_AXIS
		input wire  s00_axis_aclk,
		input wire  s00_axis_aresetn,
		output wire  s00_axis_tready,
		input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
		input wire [(C_S00_AXIS_TDATA_WIDTH/8)-1 : 0] s00_axis_tstrb,
		input wire  s00_axis_tlast,
		input wire  s00_axis_tvalid
	);
	// Add user logic here
	
    demo_model #(
          .C_S00_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH),
          .INPUT_BIT_WIDTH          (8)
    ) model_impl (
          .aclk           (aclk),
          .aresetn        (aresetn),
          .s00_axis_tlast (s00_axis_tlast),
          .s00_axis_tvalid(s00_axis_tvalid),
          .s00_axis_tdata (s00_axis_tdata),
          .s00_axis_tstrb (s00_axis_tstrb),
          .s00_axis_tready(s00_axis_tready),
          .classification  (classification)
      );
    
	// User logic ends

	endmodule
