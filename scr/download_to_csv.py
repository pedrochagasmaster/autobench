# flake8: noqa
# pylint: disable=line-too-long,trailing-whitespace,missing-final-newline,no-else-return,logging-fstring-interpolation,consider-using-with,unspecified-encoding
import subprocess
import logging
import argparse
import sys

from _common import FATAL_ERRORS, classificar_erro_impala, cycle_through_pools

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =============================================================================
# Helper Functions
# =============================================================================

def run_export_on_impala(query: str, output_file: str):
    """
    Executes an Impala query to export data to a CSV file.
    """
    command = [
        'impala-shell', '-k', '-i', 'dw.prod.impala.mastercard.int:21000', '--ssl',
        '--delimited', '--print_header', '--output_delimiter=,',
        '-q', query, '-o', output_file
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    
    if process.returncode == 0:
        logging.info(f"SUCCESS: Successfully exported data to {output_file}")
        logging.debug(stdout.decode()) 
        return True
    else:
        logging.error(f"ERROR: Impala command failed for output file {output_file}.")
        
        stderr_decoded = stderr.decode()
        erro_classificado = classificar_erro_impala(stderr_decoded)
        logging.warning(f"Mapped Error: {erro_classificado['categoria']}")
        
        if erro_classificado['categoria'] in FATAL_ERRORS:
            logging.error(f"FATAL ERROR ({erro_classificado['categoria']}): Stopping retries.")
            logging.error(f"Error Details:\n{erro_classificado['detalhes']}")
            sys.exit(1)
            
        logging.warning(f"Transient error detected. Details: {stderr_decoded}")
        return False


def retry_loop(query_to_run: str, output_file: str, queues: list):
    """
    Manages the retry logic for exporting data.
    """
    logging.info(f"--- Starting export process for {output_file} ---")
    
    def operation(fila):
        query_string = f"set request_pool={fila}; set mem_limit=1000g; {query_to_run}"
        logging.info(f"Attempting export with queue: {fila}")
        return run_export_on_impala(query_string, output_file)

    def on_cycle_failure(retry_cnt):
        log_msg = (f"All queues failed for export job. "
                   f"Waiting 30 seconds before retrying (Attempt {retry_cnt}).")
        logging.warning(log_msg)

    cycle_through_pools(queues, operation, on_cycle_failure)
    logging.info(f"--- Finished export process for {output_file} ---")


# =============================================================================
# Main Function
# =============================================================================

def main():
    """
    Main function to parse arguments and orchestrate the export process.
    """
    parser = argparse.ArgumentParser(
        description='Export Impala data to a raw CSV file with a retry mechanism.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--table-name',
        dest='table_name',
        help='The full name of the Impala table to export (e.g., schema.tablename).'
    ) 
    group.add_argument(
        '--query-file',
        dest='query_file',
        help='Path to a file containing the SQL SELECT query to execute and export.'
    )
    parser.add_argument(
        '--output-file',
        dest='output_file',
        required=True,
        help='The full path for the output CSV file (e.g., /path/to/output.csv). Compression must be handled by the caller.'
    )
    args = parser.parse_args() 

    # Determine the query to run based on arguments
    query_to_run = ""
    if args.table_name:
        logging.info(f"Mode: Exporting table '{args.table_name}'")
        query_to_run = f"select * from {args.table_name};"
    elif args.query_file:
        logging.info(f"Mode: Executing query from file '{args.query_file}'")
        try:
            with open(args.query_file, 'r') as f:
                query_to_run = f.read()
            if not query_to_run.strip():
                logging.error(f"ERROR: The provided query file '{args.query_file}' is empty.")
                sys.exit(1)
        except FileNotFoundError:
            logging.error(f"ERROR: The query file '{args.query_file}' was not found.")
            sys.exit(1)

    filas = ["adhoc_fast", "adhoc_small", "adhoc"] 

    logging.info("--- Script Configuration ---")
    logging.info(f"Output CSV file: {args.output_file}")
    logging.info("--------------------------")

    retry_loop(query_to_run, args.output_file, filas)

    logging.info(f"Export job for {args.output_file} is complete.")


if __name__ == '__main__':
    main()