import httpx
import time
import json
import xml.etree.ElementTree as ET

RUNDECK_URL = "http://rundeck:4440"
TOKEN = "portal-console-static-token"
headers = {
    "X-Rundeck-Auth-Token": TOKEN,
    "Accept": "application/json"
}

def wait_for_rundeck():
    print("Waiting for Rundeck to start up...")
    for _ in range(30):
        try:
            r = httpx.get(f"{RUNDECK_URL}/api/57/projects", headers=headers, timeout=2.0)
            if r.status_code == 200:
                print("Rundeck is ready!")
                return True
        except Exception:
            pass
        time.sleep(2.0)
    print("Rundeck startup timeout.")
    return False

def get_jobs_detail(project_name):
    # Fetch job list
    url = f"{RUNDECK_URL}/api/57/project/{project_name}/jobs"
    r = httpx.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Failed to fetch jobs for project {project_name}: {r.status_code}")
        return []
    
    jobs = r.json()
    jobs_detail = []
    
    for job in jobs:
        job_id = job["id"]
        job_name = job["name"]
        
        # Fetch detailed job definition in XML format to easily read workflow commands
        # H2 DB metadata is most reliable this way
        xml_headers = {
            "X-Rundeck-Auth-Token": TOKEN,
            "Accept": "application/xml"
        }
        detail_url = f"{RUNDECK_URL}/api/57/job/{job_id}"
        r_xml = httpx.get(detail_url, headers=xml_headers)
        if r_xml.status_code != 200:
            print(f"Failed to fetch details for job {job_name}: {r_xml.status_code}")
            continue
            
        try:
            # Parse workflow and options
            root = ET.fromstring(r_xml.content)
            job_node = root.find("job")
            
            description = job_node.find("description").text if job_node.find("description") is not None else ""
            group = job_node.find("group").text if job_node.find("group") is not None else ""
            
            # Extract options (like command, node filters, environment variables)
            context = job_node.find("context")
            project = context.find("project").text if context is not None and context.find("project") is not None else ""
            
            # Workflow steps
            sequence = job_node.find("sequence")
            steps = []
            if sequence is not None:
                for command in sequence.findall("command"):
                    # Inline script / command execution
                    exec_cmd = command.find("exec")
                    script = command.find("script")
                    if exec_cmd is not None:
                        steps.append({"type": "exec", "command": exec_cmd.text})
                    elif script is not None:
                        steps.append({"type": "script", "command": script.text})
            
            jobs_detail.append({
                "id": job_id,
                "name": job_name,
                "group": group,
                "description": description,
                "project": project_name,
                "steps": steps
            })
        except Exception as e:
            print(f"Error parsing job {job_name}: {e}")
            
    return jobs_detail

def dump():
    if not wait_for_rundeck():
        return
    
    r = httpx.get(f"{RUNDECK_URL}/api/57/projects", headers=headers)
    projects = r.json()
    print(f"Found Rundeck Projects: {[p['name'] for p in projects]}")
    
    all_jobs = []
    for p in projects:
        project_name = p["name"]
        jobs = get_jobs_detail(project_name)
        all_jobs.extend(jobs)
        
    print("\n=== EXTRACTED RUNDECK JOBS ===")
    print(json.dumps(all_jobs, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    dump()
