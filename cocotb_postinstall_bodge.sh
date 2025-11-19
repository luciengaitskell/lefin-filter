install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libcocotbutils.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libgpilog.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libgpi.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libpygpilog.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libembed.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libcocotbvpi_icarus.vpl
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libcocotb.so
install_name_tool -delete_rpath @loader_path .venv/lib/python3.12/site-packages/cocotb/libs/libcocotbvpi_verilator.so
