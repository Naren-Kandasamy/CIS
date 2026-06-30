import logging
import time

def handler(event, context):
    logger = logging.getLogger()
    logger.info('Hello from main.py')

    '''Event Functionalities'''
    raw_data = event.get_raw_data()  # raw event data
    logging.info('raw data: ' + str(raw_data))

    '''Context Functionalities -- check our actual time budget'''
    max_time = context.get_max_execution_time_ms()
    remaining_at_start = context.get_remaining_execution_time_ms()
    logging.info(f'max_execution_time_ms: {max_time}')
    logging.info(f'remaining_execution_time_ms at start: {remaining_at_start}')

    '''Sleep test -- proves whether we actually get more than 30 seconds'''
    logging.info('Starting 6.5-min sleep to test timeout budget')
    time.sleep(400)
    remaining_after_sleep = context.get_remaining_execution_time_ms()
    logging.info(f'Survived 6.5 seconds. remaining_execution_time_ms now: {remaining_after_sleep}')

    context.close_with_success()
