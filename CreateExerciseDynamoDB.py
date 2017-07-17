import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Exercises')
table.put_item(
    Item={
        "ExerciseName": "overhead press",
        "MuscleGroup": "shoulder",
        "HowTo": "https://www.youtube.com/watch?v=F3QY5vMz_6I",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=eozdVDA78K0",
        "MuscleGroup": "chest",
        "ExerciseName": "fly",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=9efgcAjQe7E",
        "MuscleGroup": "back",
        "ExerciseName": "bent over row",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=qEwKCR5JCog",
        "MuscleGroup": "shoulder",
        "ExerciseName": "shoulder press",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=Dy28eq2PjcM",
        "MuscleGroup": "legs",
        "ExerciseName": "squat",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=Ir8IrbYcM8w",
        "MuscleGroup": "back",
        "ExerciseName": "pull up",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=-4qRntuXBSc",
        "MuscleGroup": "back",
        "ExerciseName": "deadlift",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=d_KZxkY_0cM",
        "MuscleGroup": "arms",
        "ExerciseName": "skull crusher",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=W1SD96lrudY",
        "MuscleGroup": "legs",
        "ExerciseName": "leg press",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=gRVjAtPip0Y",
        "MuscleGroup": "chest",
        "ExerciseName": "bench press",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=dQqApCGd5Ss",
        "MuscleGroup": "legs",
        "ExerciseName": "step up",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=ykJmrZ5v0Oo",
        "MuscleGroup": "arms",
        "ExerciseName": "biceps curl",
        "UserID": "universal"
    }
)
table.put_item(
    Item={
        "HowTo": "https://www.youtube.com/watch?v=YbX7Wd8jQ-Q",
        "MuscleGroup": "arms",
        "ExerciseName": "triceps extension",
        "UserID": "universal"
    }
)
