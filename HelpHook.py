import time
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response


""" --- Functions that control the bot's behavior --- """


def get_help(intent_request):
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {
                     'contentType': 'PlainText',
                     'content': 'If you want to record an exercise, say \'I did #EXERCISE for #WEIGHT weight #REPS '
                                'reps and #SETS sets.\' If you want to record a run, say \'I ran #DISTANCE in '
                                '#DURATION.\'(incline is optional). If you want to record a meal, say \'I ate #NUM '
                                '#GRAMS OR SERVINGS of #FOOD.\' If you want to remember what you did on a certain day, '
                                'say \'tell me about #DAY.\' If you want to see your progression on an exercise, '
                                'say \'Show me my record with #EXERCISE.\' If you want to see all the excuses you\'ve '
                                'given, say \'Make me disappointed in myself\' If you want to set your own '
                                'nutrition goals, say \'I would like to set my own nutrition goals.\' If you want to '
                                'set your own workout, say \'I would like to set my own workout\' '
                 })


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'Help':
        return get_help(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')


""" --- Main handler --- """


def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """
    # By default, treat the user request as coming from the America/New_York time zone.
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    logger.debug('event.bot.name={}'.format(event['bot']['name']))

    return dispatch(event)
