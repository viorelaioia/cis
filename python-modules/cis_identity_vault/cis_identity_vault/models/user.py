"""Governs crud operations for profiles in the identity vault.
user_profile must be passed to this in the form required by dynamodb
{
    'id': 'ad|foo',
    'uuid': 'dc8cbad4-4426-406f-998e-9d95edb06bdc',
    'primary_email': 'foo@xyz.com',
    'sequence_number': '123456',
    'primary_email': 'foomcbar',
    'profile': 'jsondumpofuserfullprofile'
}
"""
import json
import logging
import uuid
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from botocore.exceptions import ParamValidationError


logger = logging.getLogger(__name__)


class Profile(object):
    def __init__(self, dynamodb_table_resource=None, dynamodb_client=None, transactions=True):
        """Take a dynamodb table resource to use for operations."""
        self.table = dynamodb_table_resource
        self.client = dynamodb_client
        self.transactions = transactions

    def _run_transaction(self, transact_items):
        response = self.client.transact_write_items(
            TransactItems=transact_items, ReturnConsumedCapacity="TOTAL", ReturnItemCollectionMetrics="SIZE"
        )
        return response

    def create(self, user_profile):
        if self.transactions:
            res = self._create_with_transaction(user_profile)
        else:
            res = self._create_without_transaction(user_profile)

        if res.get("ResponseMetadata", False):
            status_code = res["ResponseMetadata"]["HTTPStatusCode"]
            sequence_number = user_profile["sequence_number"]

        return {"status": status_code, "sequence_number": sequence_number}

    def _create_without_transaction(self, user_profile):
        if user_profile["sequence_number"] is None:
            user_profile["sequence_number"] = str(uuid.uuid4().int)
        return self.table.put_item(Item=user_profile)

    def _create_with_transaction(self, user_profile):
        if user_profile["sequence_number"] is None:
            user_profile["sequence_number"] = str(uuid.uuid4().int)
        transact_items = {
            "Put": {
                "Item": {
                    "id": {"S": user_profile["id"]},
                    "uuid": {"S": user_profile["uuid"]},
                    "profile": {"S": user_profile["profile"]},
                    "primary_email": {"S": user_profile["primary_email"]},
                    "primary_username": {"S": user_profile["primary_username"]},
                    "sequence_number": {"S": user_profile["sequence_number"]},
                },
                "ConditionExpression": "attribute_not_exists(id)",
                "TableName": self.table.name,
                "ReturnValuesOnConditionCheckFailure": "NONE",
            }
        }
        return self._run_transaction([transact_items])

    def update(self, user_profile):
        if self.transactions:
            res = self._update_with_transaction(user_profile)
        else:
            res = self._update_without_transaction(user_profile)
        return res

    def _update_with_transaction(self, user_profile):
        transact_items = {
            "Update": {
                "Key": {"id": {"S": user_profile["id"]}},
                "ExpressionAttributeValues": {
                    ":p": {"S": user_profile["profile"]},
                    ":u": {"S": user_profile["uuid"]},
                    ":pe": {"S": user_profile["primary_email"]},
                    ":pn": {"S": user_profile["primary_username"]},
                    ":sn": {"S": user_profile["sequence_number"]},
                },
                "ConditionExpression": "attribute_exists(id)",
                "UpdateExpression": "SET profile = :p, primary_email = :pe, sequence_number = :sn, uuid = :u, primary_username = :pe",
                "TableName": self.table.name,
                "ReturnValuesOnConditionCheckFailure": "NONE",
            }
        }
        return self._run_transaction([transact_items])

    def _update_without_transaction(self, user_profile):
        return self.table.put_item(Item=user_profile)

    def delete(self, user_profile):
        if self.transactions:
            res = self._delete_with_transaction(user_profile)
        else:
            res = self._delete_without_transaction(user_profile)
        return res

    def _delete_with_transaction(self, user_profile):
        transact_items = {
            "Delete": {
                "Key": {"id": {"S": user_profile["id"]}},
                "ConditionExpression": "attribute_exists(id)",
                "TableName": self.table.name,
                "ReturnValuesOnConditionCheckFailure": "NONE",
            }
        }

        return self._run_transaction([transact_items])

    def _delete_without_transaction(self, user_profile):
        return self.table.delete_item(Item=user_profile)

    def create_batch(self, list_of_profiles):
        sequence_numbers = []
        for profile in list_of_profiles:
            sequence_numbers.append(profile["sequence_number"])
        if self.transactions:
            res = self._create_items_with_transaction(list_of_profiles)

            if res.get("ResponseMetadata", False):
                status_code = res["ResponseMetadata"]["HTTPStatusCode"]

            return {"status": status_code, "sequence_numbers": sequence_numbers}
        else:
            try:
                res = self._put_items_without_transaction(list_of_profiles)
                return {"status": "200", "sequence_numbers": sequence_numbers}
            except Exception as e:
                logger.error("Could not write batch due to: {}".format(e))
                return {"status": "500", "sequence_numbers": sequence_numbers}

    def _put_items_without_transaction(self, list_of_profiles):
        with self.table.batch_writer() as batch:
            for profile in list_of_profiles:
                batch.put_item(Item=profile)

    def _create_items_with_transaction(self, list_of_profiles):
        transact_items = []
        for user_profile in list_of_profiles:
            if user_profile["sequence_number"] is None:
                user_profile["sequence_number"] = str(uuid.uuid4().int)
            transact_item = {
                "Put": {
                    "Item": {
                        "id": {"S": user_profile["id"]},
                        "uuid": {"S": user_profile["uuid"]},
                        "profile": {"S": user_profile["profile"]},
                        "primary_email": {"S": user_profile["primary_email"]},
                        "primary_username": {"S": user_profile["primary_username"]},
                        "sequence_number": {"S": user_profile["sequence_number"]},
                    },
                    "ConditionExpression": "attribute_not_exists(id)",
                    "TableName": self.table.name,
                    "ReturnValuesOnConditionCheckFailure": "NONE",
                }
            }
            transact_items.append(transact_item)
        logger.debug("Attempting to create batch of transactions for: {}".format(transact_items))
        return self._run_transaction(transact_items)

    def update_batch(self, list_of_profiles):
        if self.transactions:
            res = self._update_batch_with_transaction(list_of_profiles)
        else:
            res = self._put_items_without_transaction(list_of_profiles)
        return res

    def _update_batch_with_transaction(self, list_of_profiles):
        transact_items = []
        for user_profile in list_of_profiles:
            transact_item = {
                "Update": {
                    "Key": {"id": {"S": user_profile["id"]}},
                    "ExpressionAttributeValues": {
                        ":p": {"S": user_profile["profile"]},
                        ":u": {"S": user_profile["uuid"]},
                        ":pe": {"S": user_profile["primary_email"]},
                        ":pn": {"S": user_profile["primary_username"]},
                        ":sn": {"S": user_profile["sequence_number"]},
                    },
                    "ConditionExpression": "attribute_exists(id)",
                    "UpdateExpression": "SET profile = :p, primary_email = :pe, sequence_number = :sn, uuid = :u, primary_username = : pn",
                    "TableName": self.table.name,
                    "ReturnValuesOnConditionCheckFailure": "NONE",
                }
            }
            transact_items.append(transact_item)
        logger.debug("Attempting to update batch of transactions for: {}".format(transact_items))
        return self._run_transaction(transact_items)

    def find_by_id(self, id):
        result = self.table.query(KeyConditionExpression=Key("id").eq(id))
        return result

    def find_by_email(self, primary_email):
        result = self.table.query(
            IndexName="{}-primary_email".format(self.table.table_name),
            KeyConditionExpression=Key("primary_email").eq(primary_email),
        )
        return result

    def find_by_uuid(self, uuid):
        result = self.table.query(
            IndexName="{}-uuid".format(self.table.table_name), KeyConditionExpression=Key("uuid").eq(uuid)
        )
        return result

    def find_by_username(self, primary_username):
        result = self.table.query(
            IndexName="{}-primary_username".format(self.table.table_name),
            KeyConditionExpression=Key("primary_username").eq(primary_username),
        )
        return result

    @property
    def all(self):
        response = self.table.scan()
        users = response.get("Items")
        while "LastEvaluatedKey" in response:
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            users.extend(response["Items"])
        return users

    def find_or_create(self, user_profile):
        profilev2 = json.loads(user_profile["profile"])
        if len(self.find_by_id(profilev2["user_id"]["value"])["Items"]) > 0:
            res = self.update(user_profile)
            logger.info("A user profile exists already for: {}".format(profilev2["user_id"]["value"]))
        else:
            res = self.create(user_profile)
            logger.info("A user profile does not exist for: {}".format(profilev2["user_id"]["value"]))
        return res

    def find_or_create_batch(self, user_profiles):
        updates = []
        creations = []
        for user_profile in user_profiles:
            profilev2 = json.loads(user_profile["profile"])
            if len(self.find_by_id(profilev2["user_id"]["value"])["Items"]) > 0:
                logger.debug("Adding profile to the list of updates to perform: {}".format(profilev2))
                updates.append(user_profile)
            else:
                logger.debug("Adding profile to the list of creations to perform: {}".format(profilev2))
                creations.append(user_profile)

        try:
            if len(creations) > 0:
                res_create = self.create_batch(creations)
                logger.info("There are {} creations to perform in this batch.".format(res_create))
            else:
                res_create = None
        except ClientError as e:
            res_create = None
            logger.error("Could not run batch transaction due to: {}".format(e))
        except ParamValidationError as e:
            res_create = None
            logger.error("Could not run batch transaction due to: {}".format(e))

        try:
            if len(updates) > 0:
                res_update = self.update_batch(updates)
                logger.error("There are {} updates to perform in this batch.".format(len(updates)))
            else:
                res_update = None
        except ClientError as e:
            res_update = None
            logger.error("Could not run batch transaction due to: {}".format(e))
        except ParamValidationError as e:
            res_update = None
            logger.error("Could not run batch transaction due to: {}".format(e))

        logger.info("Updates were: {}".format(len(updates)))
        logger.info("Creates were: {}".format(len(creations)))

        return [res_create, res_update]

    def all_by_page(self, next_page=None, limit=25):
        if next_page is not None:
            response = self.table.scan(Limit=limit, ExclusiveStartKey=next_page)
        else:
            response = self.table.scan(Limit=limit)
        return response
