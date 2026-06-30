import logging
import time

def handler(job_request, context):
    logger = logging.getLogger()
    logger.info('Hello from main.py')

    '''JobRequest Functionalities'''
    job_details = job_request.get_job_details()
    job_meta_details = job_request.get_job_meta_details()
    all_job_params = job_request.get_all_job_params()
    logging.info(f'job_details: {job_details}')
    logging.info(f'job_meta_details: {job_meta_details}')
    logging.info(f'all_job_params: {all_job_params}')

    '''Context Functionalities -- check our actual time budget'''
    max_time = context.get_max_execution_time_ms()
    remaining_at_start = context.get_remaining_execution_time_ms()
    logging.info(f'max_execution_time_ms: {max_time}')
    logging.info(f'remaining_execution_time_ms at start: {remaining_at_start}')

    '''Sleep test -- same as the other function, for comparison'''
    logging.info('Starting 60-second sleep to test timeout budget')
    time.sleep(60)
    remaining_after_sleep = context.get_remaining_execution_time_ms()
    logging.info(f'Survived 60 seconds. remaining_execution_time_ms now: {remaining_after_sleep}')

    context.close_with_success()
