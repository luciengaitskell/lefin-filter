package connector_pkg;
  typedef enum int {
    COMBINATIONAL = 0,
    SEQUENTIAL = 1
  } logic_style;
endpackage

module connector #(
    parameter connector_pkg::logic_style connectivity = connector_pkg::COMBINATIONAL,
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
      connector_pkg::COMBINATIONAL: begin : comb_connect
        always_comb begin
          out = in;
          out_valid = in_valid;
        end
      end
      connector_pkg::SEQUENTIAL: begin : seq_connect
        always_ff @(posedge clk) begin
          out <= in;
          out_valid <= in_valid;
        end
      end
    endcase
  endgenerate

endmodule
