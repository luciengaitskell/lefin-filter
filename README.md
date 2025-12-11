# LEFIN-Filter

Line-rate Ethernet Frame Inline Network Filter

> Achieves 99% accuracy on the [USTC-TFC2016](https://github.com/davidyslu/USTC-TFC2016) dataset

[**View the writeup here**](https://github.com/user-attachments/files/24094593/lefin-filter.pdf)

### Hardware

- RealDigital 4x2 RFSoC (ZYNQ Ultrascale+ ZU48DR)
- Mellanox ConnectX-4 Lx EN (MCX4121A-ACAT)
- QSFP28 to 4xSFP28 Direct Attach Copper cable

---

MIT 6.S965:
Digital Systems Laboratory II
(Fall 2025)

---

### Simulation

```
# Run the axis_conv1d test
uv run -m sim.nn.test_axis_conv1d
```

### Model

```
# Preprocess the dataset
uv run -m model.dataset --layer l2 --mode packet

# Train the model
uv run -m model.model --dataset-layer l2

# Export weights to SystemVerilog
uv run -m model.export_weights --ckpt model/checkpoints/ustc_packet_l2/best_int8.pt --out hdl/model/includes/model_params.svh
```

### Vivado

1. Launch vivado from repo directory
2. Run `vivado.tcl` script from Vivado

### Evaluation

```
uv run replay_filter_eval.py run --tx eth0 --rx eth1 --payload-layer l2 --count 5000
```
