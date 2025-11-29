// typedef enum int {
//   COMBINATIONAL = 0,
//   SEQUENTIAL = 1
// } logic_style;


module connector #(
    parameter integer connectivity = 0,
    parameter integer WIDTH = 8
) (
    input wire clk,
    input wire [WIDTH-1:0] in,
    input wire in_valid,
    output logic [WIDTH-1:0] out,
    output logic out_valid
);

  generate
    case (connectivity)
      0: begin : comb_connect // COMBINATIONAL
        always_comb begin
          out = in;
          out_valid = in_valid;
        end
      end
      1: begin : seq_connect
        always_ff @(posedge clk) begin
          out <= in;
          out_valid <= in_valid;
        end
      end
    endcase
  endgenerate

endmodule
