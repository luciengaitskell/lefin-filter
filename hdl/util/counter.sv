
module counter #(
    parameter  int MAXIMUM   = 64,
    localparam int BIT_WIDTH = $clog2(MAXIMUM),
    parameter  int ROLL_OVER = 1
) (
    input wire clk,
    input wire rst,
    input wire trigger,
    output logic [BIT_WIDTH-1:0] count
);

  always_ff @(posedge clk) begin
    if (rst) begin
      count <= 0;
    end else begin
      if (trigger) begin
        if (ROLL_OVER == 1) begin
          count <= (count >= (BIT_WIDTH)'(MAXIMUM - 1)) ? 0 : (count + 1);
        end else if (count < (BIT_WIDTH)'(MAXIMUM - 1)) begin
          count <= count + 1;
        end
      end
    end
  end
endmodule
