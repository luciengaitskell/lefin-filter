module synchronizer #(
    parameter DEPTH = 2,
    parameter WIDTH = 1
) (
    input wire clk,
    input wire rst,
    input wire enable,
    input wire [WIDTH-1:0] data_in,
    output logic [WIDTH-1:0] data_out
);
  logic [WIDTH-1:0] sync[DEPTH-1:0];

  always_ff @(posedge clk) begin
    if (rst) begin
      for (int i = 0; i < DEPTH; i = i + 1) begin
        sync[i] <= 0;
      end
    end else if (enable) begin
      sync[DEPTH-1] <= data_in;
      for (int i = 1; i < DEPTH; i = i + 1) begin
        sync[i-1] <= sync[i];
      end
    end
  end
  assign data_out = sync[0];
endmodule
