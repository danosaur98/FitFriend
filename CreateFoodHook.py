import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
foods = dynamodb.Table('Foods')
users = dynamodb.Table('Users')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message
        }
    }


def confirm_intent(session_attributes, intent_name, slots, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ConfirmIntent',
            'intentName': intent_name,
            'slots': slots,
            'message': message
        }
    }


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


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


""" --- Helper Functions --- """


def try_ex(func):
    """
    Call passed in function in try block. If KeyError is encountered return None.
    This function is intended to be used to safely access dictionary.

    Note that this function would have negative impact on performance.
    """

    try:
        return func()
    except KeyError:
        return None


def get_user(intent_request):
    response = users.get_item(
        Key={
            'user': intent_request['userId'],
        }
    )
    return response


def is_valid_user(user):
    if 'Item' in user:
        return True
    return False


def build_validation_result(is_valid, violated_slot, message_content):
    if message_content is None:
        return {
            "isValid": is_valid,
            "violatedSlot": violated_slot,
        }

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message': {'contentType': 'PlainText', 'content': message_content}
    }


def validate_create_food(food_name, serving, calorie, protein, carbohydrate, fat):
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def create_food(intent_request):
    food_name = get_slots(intent_request)["FoodName"]
    serving = get_slots(intent_request)["Serving"]
    calorie = get_slots(intent_request)["Calorie"]
    protein = get_slots(intent_request)["Protein"]
    carbohydrate = get_slots(intent_request)["Carbohydrate"]
    fat = get_slots(intent_request)["Fat"]
    user = get_user(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['currentIntent']['confirmationStatus']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        if not is_valid_user(user):
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {
                             'contentType': 'PlainText',
                             'content': "Glad to see you're so eager! Say \'hey fitfriend\' to get started!"
                         })
        slots = get_slots(intent_request)

        if confirmation_status == 'Denied':
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {'contentType': 'PlainText',
                          'content': 'It\'s all good in the hood!'})
        if confirmation_status == 'None':
            validation_result = validate_create_food(food_name, serving, calorie, protein, carbohydrate, fat)
            if not validation_result['isValid']:
                slots[validation_result['violatedSlot']] = None
                return elicit_slot(intent_request['sessionAttributes'],
                                   intent_request['currentIntent']['name'],
                                   slots,
                                   validation_result['violatedSlot'],
                                   validation_result['message'])
            return delegate(session_attributes, get_slots(intent_request))
        if confirmation_status == 'Confirmed':
            session_attributes['chainRecordMeal'] = True
            if not serving:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'Serving',
                    {
                        'contentType': 'PlainText',
                        'content': 'How many grams in one serving?'
                    }
                )
            elif not calorie:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'Calorie',
                    {
                        'contentType': 'PlainText',
                        'content': 'How many calories in one serving?'
                    }
                )
            elif not protein:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'Protein',
                    {
                        'contentType': 'PlainText',
                        'content': 'How many grams of protein in one serving?'
                    }
                )
            elif not carbohydrate:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'Carbohydrate',
                    {
                        'contentType': 'PlainText',
                        'content': 'How many grams of carbohydrates in one serving?'
                    }
                )
            elif not fat:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'Fat',
                    {
                        'contentType': 'PlainText',
                        'content': 'How many grams of fat in one serving?'
                    }
                )

    foods.put_item(
        Item={
            "UserID": intent_request['userId'],
            "FoodName": food_name,
            "Calorie": calorie,
            "Serving": serving,
            "Protein": protein,
            "Carbohydrate": carbohydrate,
            "Fat": fat
        }
    )
    if try_ex(lambda: session_attributes['chainRecordMeal']):
        try_ex(lambda: session_attributes.pop('chainRecordMeal'))
        return confirm_intent(
            session_attributes,
            'RecordMeal',
            {
                'FoodName': food_name,
                'Measurement': None,
                'MeasurementType': None
            },
            {
                'contentType': 'PlainText',
                'content': 'Got it! {} has been added to your foods. Would you like to finish inputting your '
                           'meal?'.format(food_name)
            }
        )
    else:
        return close(intent_request['sessionAttributes'],
                     'Fulfilled',
                     {'contentType': 'PlainText',
                      'content': 'Got it! {} has been added to your foods'.format(food_name)})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'CreateFood':
        return create_food(intent_request)

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
