import serial
import argparse
import sys

# Check OS platform for msvcrt module
if sys.platform == 'win32':
    import msvcrt

UART_COM_PORT = "COM12"
UART_BAUD_RATE = 9600
HISTORY_LOG_FILE_PATH = ""

def parse_cmd_args():
    """
    /*
     * @brief Parses command-line arguments to override configurations.
     * @return argparse.Namespace Parsed arguments.
     */
    """
    parser = argparse.ArgumentParser(description="Read and format serial data")
    parser.add_argument("-p", "--port", type=str, default=UART_COM_PORT, help="Specify the COM port (e.g., COM13)")
    parser.add_argument("-b", "--baud", type=int, default=UART_BAUD_RATE, help="Specify the baud rate (e.g., 115200)")
    
    parsed_args = parser.parse_args()
    
    # Return parsed arguments
    return parsed_args

def render_buffer_inline(byte_buf):
    """
    /*
     * @brief Formats and prints the buffer inline using carriage return to overwrite.
     * @param byte_buf List of current bytes.
     * @return None
     */
    """
    # Check if buffer is empty
    if not byte_buf:
        # Exit function as there is nothing to render
        return
        
    hex_blocks = []
    char_blocks = []
    
    # Iterate over the buffer in 4-byte chunks
    for i in range(0, len(byte_buf), 4):
        chunk = byte_buf[i:i+4]
        hex_str = ""
        char_str = ""
        
        # Iterate through bytes in the current chunk
        for val in chunk:
            hex_str += f"{val:02X}"
            unicode_char = chr(val)
            
            # Verify if character is printable
            if not unicode_char.isprintable():
                unicode_char = "."
                
            char_str += unicode_char
            
        hex_blocks.append(hex_str)
        char_blocks.append(char_str)
        
    hex_part = " ".join(hex_blocks)
    char_part = " ".join(char_blocks)
    
    padded_hex = f"{hex_part:<35}"
    padded_char = f"{char_part:<19}"
    
    # Output string with carriage return to overwrite the current line
    print(f"\r{padded_hex}               {padded_char}", end="", flush=True)
    
    # Return control to caller
    return

def read_and_format_serial(port_name, baud_rate):
    """
    /*
     * @brief Opens COM port and reads/formats incoming bytes continuously in 16-byte chunks.
     * @param port_name The COM port string to open.
     * @param baud_rate The baud rate for the connection.
     * @return None
     */
    """
    # Attempt connection to serial port
    try:
        ser = serial.Serial(port_name, baudrate=baud_rate, timeout=0.1)
    # Handle connection error
    except serial.SerialException as e:
        print(f"Failed to open {port_name} at {baud_rate} bps: {e}")
        # Exit function on failure
        return

    print(f"Listening on {port_name} at {baud_rate} bps... (Press Enter to insert newline, Ctrl+C to stop)\n")
    
    byte_buffer = []

    # Handle manual script termination
    try:
        # Loop continuously for data
        while True:
            # Check for keyboard hit on Windows
            if sys.platform == 'win32' and msvcrt.kbhit():
                key = msvcrt.getch()
                
                # Check if Enter key is pressed
                if key == b'\r':
                    # Move to the next line
                    print()
                    byte_buffer.clear()
            
            data = ser.read(1)
            
            # Check if serial data is received
            if data:
                byte_buffer.append(data[0])
                render_buffer_inline(byte_buffer)
                
                # Check if buffer reached 16 bytes limit
                if len(byte_buffer) == 16:
                    # Move to the next line and clear buffer
                    print()
                    byte_buffer.clear()
                
    # Catch interrupt signal
    except KeyboardInterrupt:
        # Move to new line to prevent overwriting prompt
        print()
        print("Exiting script...")
        
    ser.close()
    
    # Return control to caller
    return

# Check if script is executed as main program
if __name__ == "__main__":
    args = parse_cmd_args()
    
    # Override port if provided
    if args.port:
        UART_COM_PORT = args.port
        
    # Override baud rate if provided
    if args.baud:
        UART_BAUD_RATE = args.baud
        
    read_and_format_serial(UART_COM_PORT, UART_BAUD_RATE)


# 
# 
# import serial
# import argparse
# import sys
# 
# # Import msvcrt module for Windows OS to handle non-blocking keyboard input
# if sys.platform == 'win32':
#     import msvcrt
# 
# UART_COM_PORT = "COM12"
# UART_BAUD_RATE = 9600
# HISTORY_LOG_FILE_PATH = ""
# 
# def parse_cmd_args():
#     """
#     /*
#      * @brief Parses command-line arguments to override configurations.
#      * @return argparse.Namespace Parsed arguments.
#      */
#     """
#     parser = argparse.ArgumentParser(description="Read and format serial data")
#     parser.add_argument("-p", "--port", type=str, default=UART_COM_PORT, help="Specify the COM port (e.g., COM13)")
#     parser.add_argument("-b", "--baud", type=int, default=UART_BAUD_RATE, help="Specify the baud rate (e.g., 115200)")
#     
#     parsed_args = parser.parse_args()
#     
#     # Return parsed arguments to caller
#     return parsed_args
# 
# def read_and_format_serial(port_name, baud_rate):
#     """
#     /*
#      * @brief Opens COM port and reads/formats incoming bytes continuously.
#      * @param port_name The COM port string to open.
#      * @param baud_rate The baud rate for the connection.
#      * @return None
#      */
#     """
#     # Attempt to open serial port with a short timeout for responsive key presses
#     try:
#         ser = serial.Serial(port_name, baudrate=baud_rate, timeout=0.1)
#     # Handle connection errors gracefully
#     except serial.SerialException as e:
#         print(f"Failed to open {port_name} at {baud_rate} bps: {e}")
#         # Exit function on failure
#         return
# 
#     print(f"Listening on {port_name} at {baud_rate} bps... (Press Enter to insert newline, Ctrl+C to stop)\n")
# 
#     # Handle manual script termination
#     try:
#         # Loop continuously for incoming serial data and keyboard events
#         while True:
#             # Check if OS is Windows and a keyboard key was pressed
#             if sys.platform == 'win32' and msvcrt.kbhit():
#                 key = msvcrt.getch()
#                 
#                 # Check if the pressed key is Enter (carriage return)
#                 if key == b'\r':
#                     print()
#             
#             data = ser.read(1)
#             
#             # Check if serial data is received
#             if data:
#                 val = data[0]
#                 bin_val = f"{val:08b}"
#                 formatted_bin = f"{bin_val[:4]}_{bin_val[4:]}B"
#                 hex_val = f"{val:02X}H"
#                 
#                 unicode_char = chr(val)
#                 
#                 # Check if character is non-printable to replace with a dot
#                 if not unicode_char.isprintable():
#                     unicode_char = "."
#                     
#                 print(f"{formatted_bin}\t\t{hex_val}\t\t{unicode_char}")
#                 
#     # Catch keyboard interrupt
#     except KeyboardInterrupt:
#         print("\nExiting script...")
#         
#     ser.close()
#     
#     # Return control to caller
#     return
# 
# # Check if script is executed directly
# if __name__ == "__main__":
#     args = parse_cmd_args()
#     
#     # Update UART port if argument is provided
#     if args.port:
#         UART_COM_PORT = args.port
#         
#     # Update UART baud rate if argument is provided
#     if args.baud:
#         UART_BAUD_RATE = args.baud
#         
#     read_and_format_serial(UART_COM_PORT, UART_BAUD_RATE)
# 
# 
