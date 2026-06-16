# flake8: noqa
# pylint: disable=line-too-long,trailing-whitespace,missing-final-newline,logging-fstring-interpolation,too-many-locals,f-string-without-interpolation,unspecified-encoding
import logging
import argparse
import sys
from datetime import datetime, timedelta
import calendar

# --- Import functions from the main script ---
# Assumes Query_Impala_Parametrized.py is in the same directory on the remote server.
try:
    from Query_Impala_Parametrized import run_on_impala
    from _common import cycle_through_pools, send_email
except ImportError:
    logging.error("Fatal Error: Could not import functions from Query_Impala_Parametrized.py.")
    sys.exit(1)

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def monthly_range(start_date, end_date):
    """Generator for iterating through the first day of each month in a date range."""
    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        yield current_date
        current_date = (current_date + timedelta(days=32)).replace(day=1)

def execute_step_with_retry(query: str, operation_desc: str, args):
    """
    Manages the retry logic for a single step using the imported run_on_impala function.
    """
    logging.info(f"--- Starting Step: {operation_desc} ---")
    filas = ["adhoc_fast", "adhoc_small", "acs_small", "acs_large", "adhoc"]
    def operation(fila):
        full_query = f"set request_pool={fila}; {query}"
        step_subject = f"{args.subject} - Step: {operation_desc}"
        finished = run_on_impala(
            query=full_query,
            subject=step_subject,
            to_email=args.to_email,
            tablecreated=operation_desc,
            user=args.user,
            queue=fila
        )
        if finished:
            logging.info(f"Step '{operation_desc}' finished on queue {fila}. Check email notifications for final status.")
        return finished

    def on_cycle_failure(_retry_cnt):
        logging.warning(f"All queues failed for step '{operation_desc}' with retryable errors. Waiting 30 seconds.")

    try:
        cycle_through_pools(filas, operation, on_cycle_failure, max_cycles=10)
    except TimeoutError as exc:
        raise TimeoutError(f"Step '{operation_desc}' failed after 10 retry cycles. Halting job.") from exc

# --- NEW Core Processing Function ---

def process_monthly_job(args):
    """
    Orchestrates the entire monthly partitioned job from planning to cleanup.
    """
    # 1. Planning and Initial Notification
    start_date = datetime.strptime(args.start_date, "%m/%d/%Y")
    end_date = datetime.strptime(args.end_date, "%m/%d/%Y")

    # HDFS storage prefix is the schema's leading segment (e.g. aa_enc -> aa,
    # coe_enc -> coe), matching the table_wrapper used by Query_Impala. This
    # previously hardcoded "coe", silently writing aa_enc tables under
    # /das/coe/enc/. coe_enc jobs are unaffected (coe_enc still -> coe).
    schema_prefix = args.schema.split("_", 1)[0]

    planned_temp_tables = []
    for date in monthly_range(start_date, end_date):
        dt_ano_mes = date.strftime('%Y%m')
        temp_table_name = f"{args.schema}.{args.table_name}_temp_{dt_ano_mes}"
        planned_temp_tables.append(temp_table_name)
    
    final_table_name = f"{args.schema}.{args.table_name}_fulljoin"
    plan_message = (f"Monthly partitioned job has started.\n\nExecution Plan:\n-----------------\n"
                    f"1. The following temporary tables will be created:\n")
    for tbl in planned_temp_tables:
        plan_message += f"   - {tbl}\n"
    plan_message += (f"\n2. The temporary tables will be joined into the final table:\n   - {final_table_name}\n\n"
                     f"3. All temporary tables will be deleted upon completion.\n\n"
                     f"You will receive further notifications as the job progresses.")
    send_email(plan_message, f"{args.subject} - Job Started (Execution Plan)", args.to_email)
    
    with open(args.sql_file, 'r') as f:
        sql_template = f.read()
    
    # 2. Create Monthly Tables
    for date in monthly_range(start_date, end_date):
        month_end_day = calendar.monthrange(date.year, date.month)[1]
        month_end_date = date.replace(day=month_end_day)
        date_inicio_str, date_fim_str = str(date.date()), str(month_end_date.date())
        dt_ano_mes = date.strftime('%Y%m')
        
        temp_table_name = f"{args.schema}.{args.table_name}_temp_{dt_ano_mes}"
        monthly_sql = sql_template.format(date_inicio=date_inicio_str, date_fim=date_fim_str)
        
        create_temp_table_query = f"""
            DROP TABLE IF EXISTS {temp_table_name};
            CREATE TABLE {temp_table_name}
            STORED AS parquet LOCATION '/das/{schema_prefix}/enc/{args.user}/{args.table_name}_temp_{dt_ano_mes}'
            AS
            {monthly_sql}
        """
        execute_step_with_retry(create_temp_table_query, f"Create temp table {temp_table_name}", args)

    # 3. Join Tables into Final Table
    union_query_parts = [f"SELECT * FROM {table}" for table in planned_temp_tables]
    union_query = "\nUNION ALL\n".join(union_query_parts)
    
    create_final_table_query = f"""
        DROP TABLE IF EXISTS {final_table_name};
        CREATE TABLE {final_table_name}
        STORED AS parquet LOCATION '/das/{schema_prefix}/enc/{args.user}/{args.table_name}_fulljoin' AS
        {union_query}
    """
    execute_step_with_retry(create_final_table_query, f"Create final table {final_table_name}", args)

    # 4. Cleanup Temporary Tables
    for table in planned_temp_tables:
        drop_query = f"DROP TABLE IF EXISTS {table}"
        execute_step_with_retry(drop_query, f"Drop temp table {table}", args)
        
    send_email("The entire monthly partitioned job has completed.", f"{args.subject} - Job Finished", args.to_email)


# --- Main Entry Point ---
def main():
    """
    Parses arguments and calls the main processing function.
    """
    parser = argparse.ArgumentParser(description='Run a monthly-partitioned Impala query job.')
    parser.add_argument('--sql-file', required=True, help='Path to the .sql template file.')
    parser.add_argument('--schema', required=True, help='Target schema.')
    parser.add_argument('--table-name', required=True, help='Base name for the final table.')
    parser.add_argument('--start-date', required=True, help='Start date (MM/DD/YYYY).')
    parser.add_argument('--end-date', required=True, help='End date (MM/DD/YYYY).')
    parser.add_argument('--user', required=True, help='Remote user ID (eid).')
    parser.add_argument('--to-email', required=True, help='Recipient email address.')
    parser.add_argument('--subject', required=True, help='Base subject for emails.')
    args = parser.parse_args()

    try:
        process_monthly_job(args)
    except Exception as e:
        logging.error(f"A critical error occurred in the monthly job orchestrator: {e}")
        send_email(f"The monthly partitioned job failed with a critical error in the main script:\n\n{e}", f"{args.subject} - JOB FAILED", args.to_email)
        sys.exit(1)

if __name__ == '__main__':
    main()