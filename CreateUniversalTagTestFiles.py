import json
import os

DATA_DIRS = os.path.dirname(os.path.realpath(__file__)) + "/tests/data/placebo/"
folder_list = [folder for folder in os.listdir(DATA_DIRS) if os.path.isdir(os.path.join(DATA_DIRS, folder))]

for folder in folder_list:
    for file in os.listdir(DATA_DIRS + folder):
        if "ec2.CreateTags" in file:
            with open(DATA_DIRS + folder + "/" + file, "r") as f:
                data = json.load(f)
                new_json = data
                if data["data"]["ResponseMetadata"] == {}:
                    new_json["data"]["FailedResourcesMap"] = {}
                elif "HTTPHeaders" in data["data"]["ResponseMetadata"]:
                    new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["content-type"] = "application/x-amz-json-1.1"
                    if "vary" in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        del new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["vary"]
                    if "transfer-encoding" in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        del new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["transfer-encoding"]
                    if "content-length" not in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["content-length"] = "25"
                    new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["x-amzn-requestid"] = new_json["data"]["ResponseMetadata"]["RequestId"]
                suffix = ""
                if "_" in file:
                    suffix = "_" + file.rsplit("_",1)[1].split(".")[0]
                with open(DATA_DIRS + folder + "/tagging.TagResources"+suffix+".json", "wt+") as f2:
                    json.dump(new_json, f2, indent=2)
                    print(new_json)

        if "ec2.DeleteTags" in file:
            with open(DATA_DIRS + folder + "/" + file, "r") as f:
                data = json.load(f)
                new_json = data
                if data["data"]["ResponseMetadata"] == {}:
                    new_json["data"]["FailedResourcesMap"] = {}
                elif "HTTPHeaders" in data["data"]["ResponseMetadata"]:
                    new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["content-type"] = "application/x-amz-json-1.1"
                    if "vary" in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        del new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["vary"]
                    if "transfer-encoding" in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        del new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["transfer-encoding"]
                    if "content-length" not in data["data"]["ResponseMetadata"]["HTTPHeaders"]:
                        new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["content-length"] = "0"
                    new_json["data"]["ResponseMetadata"]["HTTPHeaders"]["x-amzn-requestid"] = new_json["data"]["ResponseMetadata"]["RequestId"]
                suffix = ""
                if "_" in file:
                    suffix = "_" + file.rsplit("_",1)[1].split(".")[0]
                with open(DATA_DIRS + folder + "/tagging.UntagResources"+suffix+".json", "wt+") as f2:
                    json.dump(new_json, f2, indent=2)
                    print(new_json)