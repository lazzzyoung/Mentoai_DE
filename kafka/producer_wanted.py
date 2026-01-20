import requests
import json


def getResponse(url, headers):

    basedURL = "https://www.wanted.co.kr"
    targetURL = basedURL + url
    response = requests.get(targetURL, headers=headers)
    if(response.status_code == 200):
        print("Request Success")
        return response.json()
    else :
        print(f"Request Fail. Response Code = {response.status_code}")

def create_id_list(url, headers):
    jobs_id_list = []
    resData = getResponse(url, headers).get('data', [])
    nextLink = getResponse(url, headers).get('links', {}).get('next')

    while(nextLink is not None):
        for i in range (len(resData)):
            # print(resData[i]['id'])
            jobs_id_list.append(resData[i]['id'])
        
        url = nextLink
        nextLink = getResponse(url, headers).get('links', {}).get('next')
    
    return jobs_id_list
    

url = "/api/chaos/navigation/v1/results?1768904742653=&job_group_id=518&job_ids=655&country=kr&job_sort=job.popularity_order&years=-1&locations=all&limit=20"
headers = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36' }

# response = getResponse(url, headers)

    

jobList = create_id_list(url, headers)
print(jobList)