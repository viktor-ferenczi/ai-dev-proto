from pprint import pprint
from typing import List

import requests
from pydantic import ValidationError

from ..common.config import C
from ..sonar.issue import Issue


class SonarClient:

    def __init__(self, project_name: str, token: str = '', base_url: str = ''):
        self.project_name: str = project_name
        self.token: str = token or C.SONAR_TOKEN
        self.base_url: str = base_url or C.SONAR_BASE_URL

    # FIXME: Add optional filter conditions to allow for optimized retrieval instead of post-filtering
    def get_issues(self) -> List[Issue]:
        issues: List[Issue] = []

        current_page = 1
        last_page = 1

        while current_page <= last_page:

            json_data = self.__get_page_of_issues(current_page)
            for data in json_data['issues']:
                try:
                    issue = Issue(**data)
                except ValidationError as e:
                    print('-' * 80)
                    pprint('Issue data:')
                    pprint(data)
                    print('-' * 80)
                    raise

                issues.append(issue)

            d_pages = json_data['paging']['total'] / json_data['paging']['pageSize']
            last_page = int(d_pages) + 1
            current_page += 1

        return issues

    def __get_page_of_issues(self, current_page):
        url = f"{self.base_url}/api/issues/search?pageSize=500&componentKeys={self.project_name}&ps=500&p={current_page}"
        headers = {
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
        json_data = response.json()
        return json_data


def test():
    sonar = SonarClient('Project', C.SONAR_TOKEN)
    issues = sonar.get_issues()

    for issue in issues:
        pprint(issue)


if __name__ == '__main__':
    test()
