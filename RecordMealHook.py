import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
food_log = dynamodb.Table('FoodLog')
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


def is_valid_user(intent_request):
    response = users.get_item(
        Key={
            'UserID': intent_request['userId'],
        }
    )
    if 'Item' in response:
        return True
    return False


def condense_measurement_type(measurement_type):
    if measurement_type is not None:
        if measurement_type.lower() in ['grams', 'gram', 'g']:
            return 'grams'
        elif measurement_type.lower() in ['servings', 'serving']:
            return 'servings'


def calculate_nutrition(food_name, measurement, measurement_type, intent_request):
    food_information = foods.get_item(
        Key={
            'UserID': intent_request['userId'],
            'FoodName': food_name.lower()
        }
    )
    calorie, protein, carbohydrate, fat = None, None, None, None
    if measurement_type == 'servings':
        calorie = int(measurement) * int(food_information['Item']['Calorie'])
        protein = int(measurement) * int(food_information['Item']['Protein'])
        carbohydrate = int(measurement) * int(food_information['Item']['Carbohydrate'])
        fat = int(measurement) * int(food_information['Item']['Fat'])
    elif measurement_type == 'grams':
        serving = int(measurement) / int(food_information['Item']['Serving'])
        calorie = serving * int(food_information['Item']['Calorie'])
        protein = serving * int(food_information['Item']['Protein'])
        carbohydrate = serving * int(food_information['Item']['Carbohydrate'])
        fat = serving * int(food_information['Item']['Fat'])
    return {'calorie': int(calorie), 'protein': int(protein), 'carbohydrate': int(carbohydrate), 'fat': int(fat)}


def get_remaining_nutrition(food_name, measurement, measurement_type, intent_request):
    meal_nutrition = calculate_nutrition(food_name, measurement, measurement_type, intent_request)
    user = users.get_item(
        Key={
            'user': intent_request['userId'],
        }
    )
    today = time.strftime("%m/%d/%Y")
    calorie = user['Item']['dailyNutrientsAndWorkouts'][today]['calorie']['remaining'] - meal_nutrition['calorie']
    protein = user['Item']['dailyNutrientsAndWorkouts'][today]['protein']['remaining'] - meal_nutrition['protein']
    carbohydrate = user['Item']['dailyNutrientsAndWorkouts'][today]['carbohydrate']['remaining'] - meal_nutrition[
        'carbohydrate']
    fat = user['Item']['dailyNutrientsAndWorkouts'][today]['fat']['remaining'] - meal_nutrition['fat']
    return {'calorie': calorie, 'protein': protein, 'carbohydrate': carbohydrate, 'fat': fat}


def is_valid_food(food_name, intent_request):
    response = foods.get_item(
        Key={
            'UserID': 'universal',
            'FoodName': food_name.lower()
        }
    )
    if 'Item' in response:
        return True
    else:
        response = foods.get_item(
            Key={
                'UserID': intent_request['userId'],
                'FoodName': food_name.lower()
            }
        )
        if 'Item' in response:
            return True
    return False


def is_valid_measurement_type(measurement_type):
    valid_measurement_types = ['grams', 'gram', 'g', 'servings', 'serving']
    return measurement_type.lower() in valid_measurement_types


def validate_record_meal(food_name, measurement, measurement_type, intent_request):
    if food_name is not None:
        if not is_valid_food(food_name, intent_request):
            return build_validation_result(False, 'FoodName', '{} is not recognized as one of your foods. Would '
                                                              'you like to add it?'.format(food_name))
    if measurement_type is not None:
        if not is_valid_measurement_type(measurement_type):
            return build_validation_result(False, 'MeasurementType', 'Sorry, was that in servings or grams?')
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def record_meal(intent_request):
    food_name = get_slots(intent_request)["FoodName"]
    measurement = get_slots(intent_request)["Measurement"]
    measurement_type = condense_measurement_type(get_slots(intent_request)["MeasurementType"])
    source = intent_request['invocationSource']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        if not is_valid_user(intent_request):
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {
                             'contentType': 'PlainText',
                             'content': "Glad to see you're so eager! Say \'hey fitfriend\' to get started!"
                         })
        slots = get_slots(intent_request)
        validation_result = validate_record_meal(food_name, measurement, measurement_type, intent_request)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            if not is_valid_food(food_name, intent_request):
                return confirm_intent(
                    session_attributes,
                    'CreateFood',
                    {
                        'FoodName': food_name,
                        'Serving': None,
                        'Calorie': None,
                        'Protein': None,
                        'Carbohydrate': None,
                        'Fat': None
                    },
                    {
                        'contentType': 'PlainText',
                        'content': '{} is not recognized as one of your foods. Would '
                                   'you like to add it?'.format(food_name)

                    }
                )
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])
        if food_name and measurement and measurement_type is not None:
            remaining_nutrition = get_remaining_nutrition(food_name, measurement, measurement_type, intent_request)
            session_attributes['RemainingCalories'] = remaining_nutrition['calorie']
            session_attributes['RemainingProtein'] = remaining_nutrition['protein']
            session_attributes['RemainingCarbohydrate'] = remaining_nutrition['carbohydrate']
            session_attributes['RemainingFat'] = remaining_nutrition['fat']
            session_attributes['Overflow'] = remaining_nutrition['overflow']
        return delegate(session_attributes, get_slots(intent_request))
    remaining_nutrition = get_remaining_nutrition(food_name, measurement, measurement_type, intent_request)
    food_log.put_item(
        Item={
            "UserID": intent_request['userId'],
            "Date": time.strftime("%m/%d/%Y %T"),
            "FoodName": food_name,
            "Measurement": measurement,
            "MeasurementType": measurement_type,
            "calorieRemaining": remaining_nutrition['calorie'],
            "proteinRemaining": remaining_nutrition['protein'],
            "carbohydrateRemaining": remaining_nutrition['carbohydrate'],
            "fatRemaining": remaining_nutrition['fat'],
        }
    )
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set dailyNutrientsAndWorkouts.#day = :d",
        ExpressionAttributeValues={
            ':d': {
                "calorieRemaining": remaining_nutrition['calorie'],
                "proteinRemaining": remaining_nutrition['protein'],
                "carbohydrateRemaining": remaining_nutrition['carbohydrate'],
                "fatRemaining": remaining_nutrition['fat'],
            }
        },
        ExpressionAttributeNames={
            '#day': time.strftime("%m/%d/%Y"),
        },
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {
                     'contentType': 'PlainText',
                     'content': "Yum!"
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
    if intent_name == 'RecordMeal':
        return record_meal(intent_request)

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
