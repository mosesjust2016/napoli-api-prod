import secrets, string, requests, re, io, uuid, base64, string
from PIL import Image
from flask import make_response, jsonify
from decouple import config
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

regex = "^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$"
bravo_key = config("BRAVO_KEY")


def list_drive_files(folder_id, service_account_file="credentials.json", scopes=["https://www.googleapis.com/auth/drive"], query=None):
        """
        List files in a specified Google Drive folder using the Google Drive API.

        :param folder_id: The ID of the Google Drive folder to list files from.
        :param service_account_file: Path to the service account key file (default: 'credentials.json').
        :param scopes: List of Google API scopes (default: ['https://www.googleapis.com/auth/drive']).
        :param query: Custom query string for filtering files (default: None).
        :return: List of files with their id, name, mimeType, and webViewLink.
        """
        try:
            # Authenticate using the service account
            creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=scopes
            )

            # Build the Drive API client
            drive_service = build("drive", "v3", credentials=creds)

            # Use provided query or default to folder-based query
            q = query if query else f"'{folder_id}' in parents and trashed=false"

            # Query files
            results = drive_service.files().list(
                q=q,
                fields="files(id, name, mimeType, webViewLink, appProperties)"
            ).execute()

            # Return the list of files
            files = results.get("files", [])
            return files

        except Exception as e:
            return {"error": str(e), "status": "failed"}

#FUNCTION TO SAVE IMAGE IN A FOLDER 
def saveimgtofile(userimage):
        
    image = base64.b64decode(str(userimage))  
    my_id = uuid.uuid4().hex     
    fileName = my_id + '.png'

    imagePath = ('upload/'+fileName)
    img = Image.open(io.BytesIO(image))
    img.save(imagePath, 'png')

    return imagePath


def savedoctofile(userdocument, file_extension):
    """
    Saves a base64-encoded Word or PDF file to the 'upload/' directory.

    :param userdocument: Base64-encoded document
    :param file_extension: 'pdf' or 'docx' (without the dot)
    :return: Path to saved file
    """
    file_extension = file_extension.lower()
    if file_extension not in ["pdf", "docx"]:
        raise ValueError("Only 'pdf' and 'docx' are supported.")

    # Decode base64 document
    document_data = base64.b64decode(str(userdocument))

    # Generate unique file name
    my_id = uuid.uuid4().hex
    fileName = f"{my_id}.{file_extension}"

    # Ensure upload folder exists
    os.makedirs("upload", exist_ok=True)

    # Save file
    filePath = os.path.join("upload", fileName)
    with open(filePath, "wb") as f:
        f.write(document_data)

    return filePath


# CONVERT RESPONSE TO JSON
def jsonifyFormat(responsedata, status_code):
    # Ensure the response data is JSON serializable
    if isinstance(responsedata, dict):
        responsedata = jsonify(responsedata)  # Convert dictionary to JSON response

    # Create the response with the desired HTTP status code
    response = make_response(responsedata)
    response.status_code = status_code  # Set the status code

    # Set the Content-Type header to application/json
    response.headers['Content-Type'] = 'application/json'

    return response


#FUNCTION TO GENERATE DIGIT CODE
def gen_len_code(length, num_only):

    code = None
    
    if num_only:
        digits = string.digits
        code = ''.join(secrets.choice(digits) for i in range(length))
    else:
        # alphabet = string.ascii_letters + string.digits
        alphabet = string.ascii_uppercase + string.digits
        code = ''.join(secrets.choice(alphabet) for i in range(length))
        
    return code

# Function for validating an email
def check_email(email):
    # Regular expression for validating email format
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_regex, email))
    


# FUNCTION TO SEND EMAIL USING BREVO API
def send_email(heading, email, name, msg):
    url = "https://api.brevo.com/v3/smtp/email"
    api_key = bravo_key

    data = {
        "sender": {"name": "noreply", "email": "noreply@molomarketing.cloud"},
        "to": [
            {"email": email, "name": name},
        ],
        "subject": heading,
        "htmlContent": msg,
    }

    headers = {
        "Accept": "application/json",
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=data, headers=headers)

        response_data = {
            "status": response.status_code,
            "iserror": "false",
            "message": "Email Sent Successfully",
        }

        return jsonify(response_data)

    except requests.exceptions.RequestException as e:
        response_data = {
            "status": 500,
            "iserror": "true",
            "message": f"Request failed: {str(e)}",
        }
    
