import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Exercises')
table.put_item(
    Item={
        "Name": "overhead press",
        "MuscleGroup": "shoulder",
        "HowTo": "https://www.youtube.com/watch?v=F3QY5vMz_6I",
        "UserID": "universal"
    }
)