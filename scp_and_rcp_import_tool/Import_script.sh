# Read the profile name from the command-line argument
profile_name="$2"

# Check if the profile name is provided
if [ -z "$profile_name" ]; then
    echo "Error: AWS profile name not provided."
    echo "Usage: $0 <profile_name>"
    exit 1
fi

# Install Python and required packages if not already installed
if ! command -v python3 &> /dev/null; then
    echo "Python3 is not installed. Installing Python3 and required packages..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
fi

# Install required Python packages
pip3 install boto3

export PROFILE_NAME="$profile_name"

# Run the code for migrating SCPs to Cloudformation
python3 main.py

