import json
import numpy as np
import base64
import random
import boto3
import datetime

# TODO: uncomment
# import cv2

# dynamo credentials
ACCESS_KEY = 'AKIAZ7JA4ZXTGCUSJ5NO'
SECRET_KEY = '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'
REGION = 'us-east-1'


def lambda_handler(event, context):
    # This part is used to get the endpoint
    kinesis_client = boto3.client('kinesisvideo')
    endpoint_response = kinesis_client.get_data_endpoint(
        StreamARN='arn:aws:kinesisvideo:us-east-1:530060456874:stream/ExampleStream/1573078203070',
        APIName='GET_MEDIA'
    )
    DataEndpoint = endpoint_response['DataEndpoint']
    print(DataEndpoint)

    # Get_media API
    video_client = boto3.client('kinesis-video-media', endpoint_url=DataEndpoint)
    stream_response = video_client.get_media(
        StreamARN='arn:aws:kinesisvideo:us-east-1:530060456874:stream/ExampleStream/1573078203070',
        StartSelector={
            'StartSelectorType': 'NOW'
        }
    )
    video_stream = stream_response['Payload'].read()
    # can use ['Payload'].read(1024 * 16384) reads min(16MB of payload, payload size)

    # Use openCV to get a frame from video_stream
    image_name = ""
    img_address = ""
    bucket = 'face-detect-6998'
    with open('/tmp/stream.mkv', 'wb') as f:
        f.write(video_stream)
        cap = cv2.VideoCapture('/tmp/stream.mkv')
        ret, frame = cap.read()
        if ret and np.shape(frame) != ():
            random.seed()
            image_name = str(random.randint(10000000, 99999999)) + '.jpg'
            cv2.imwrite('/tmp/' + image_name, frame)

            # save it into the S3 bucket
            s3_client = boto3.client('s3')
            s3_client.upload_file('/tmp/' + image_name, bucket, image_name)
            img_address = 'https://{}.s3.amazonaws.com/{}'.format(bucket, image_name)
            print(img_address)
            print('Image uploaded')
        cap.release()

    # read the data from KDS
    rekognition_client = boto3.client('rekognition')
    records = event['Records']
    faceID = ""
    for record in records:
        load = base64.b64decode(record['kinesis']['data'])
        payload = json.loads(load)
        FaceSearchResponses = payload["FaceSearchResponse"]
        for FaceSearchResponse in FaceSearchResponses:
            matched_faces = FaceSearchResponse["MatchedFaces"]
            # Get faceID. If no match, use Indexed Face. Else, parse event info
            if len(matched_faces) == 0 and image_name != "":
                index_response = rekognition_client.index_faces(
                    CollectionId='Face',
                    Image={
                        'S3Object': {
                            'Bucket': bucket,
                            'Name': image_name
                        }
                    },
                )
                faceID = index_response["FaceRecords"][0]["Face"]["FaceId"]
                print("************This is Indexed face***********", faceID)
            elif len(matched_faces) != 0:
                faceID = matched_faces[0]["Face"]["FaceId"]
                print("************This is matched face***********", faceID)

    """
    Todo
    I provide three parameters:
        img_address     Like    https://face-detect-6998.s3.amazonaws.com/28150579.jpg
                        if == "" means I get a empty frame. Just skip it
        image_name      Like    28150579.jpg
                        if == "" means I get a empty frame. Just skip it
        faceID          Like    ab4fc56d-e7c0-4502-907c-69a0435dc5c3
                        if == "" means I get a empty frame. Just skip it
    """

    if faceID:
        item = searchFace(faceID)
        if (item):
            otp(faceID, phone=item["phoneNumber"])
            appendPhoto(faceID, img_address)


    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }


# check whether faceID is in 'visitors' table
def searchFace(faceID):
    global ACCESS_KEY
    global SECRET_KEY
    global REGION
    client = boto3.client('dynamodb', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                          region_name=REGION)
    response = client.get_item(
        Key={
            "faceId": {
                "S": faceID
            }
        },
        ReturnConsumedCapacity='TOTAL',
        TableName='visitors'
    )
    try:
        if (response["Item"]):
            # print(response)
            # {
            # 'Item': {'faceId': {'S': '1'}},
            # 'ConsumedCapacity': {'TableName': 'visitors', 'CapacityUnits': 0.5},
            # 'ResponseMetadata': {'RequestId': 'DJKMDTTIQVKF10UIKR1LMA20OFVV4KQNSO5AEMVJF66Q9ASUAAJG',
            # 'HTTPStatusCode': 200, 'HTTPHeaders': {'server': 'Server', 'date': 'Fri, 15 Nov 2019 20:30:13 GMT',
            # 'content-type': 'application/x-amz-json-1.0', 'content-length': '93', 'connection': 'keep-alive',
            # 'x-amzn-requestid': 'DJKMDTTIQVKF10UIKR1LMA20OFVV4KQNSO5AEMVJF66Q9ASUAAJG', 'x-amz-crc32':
            # '2192037580'}, 'RetryAttempts': 0}}
            return response["Item"]
    except:
        return False


# generate and store otp with faceID; send otp
def otp(faceID, phone):
    global ACCESS_KEY
    global SECRET_KEY
    global REGION
    client = boto3.client('dynamodb', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                          region_name=REGION)
    OTP = str(random.randint(100000, 999999))
    TTL = str(int(datetime.datetime.now().timestamp())+300)
    # print(TTL)
    # print(type(TTL))
    item = {
        "otp": {
            "S": OTP
        },
        "faceId": {
            "S": faceID
        },
        "ttl": {
            "N": TTL
        }
    }
    response = client.put_item(
        Item=item,
        ReturnConsumedCapacity='TOTAL',
        TableName='passcodes',
    )
    sendOTP(OTP, phone)


# append a new photo to the photo array if the faceID already exists
def appendPhoto(faceID, img_address):
    global ACCESS_KEY
    global SECRET_KEY
    global REGION
    client = boto3.client('dynamodb', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                          region_name=REGION)
    timestamp = str(int(datetime.datetime.now().timestamp()))
    response = client.update_item(
        Key={
            "faceId": {
                "S": faceID
            }
        },
        ExpressionAttributeNames={
            "#C": "photos"
        },
        ExpressionAttributeValues={
            ':c': {
                'S': address["zipcode"],
            }
        },
        ReturnValues='ALL_NEW',
        TableName='visitors',
        UpdateExpression='SET #C = :c',
    )


def sendOTP(OTP, phone):
    # TODO: send otp via SMS
    pass


# searchFace("1")
# otp("1","4564")