from setuptools import setup, find_packages

setup(
    name="scp_and_rcp_import_tool",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["boto3"],
    author="Swara Gandhi",
    author_email="gandhi.swara@gmail.com",
    description="A solution to import existing SCPs and RCPs into AWS CloudFormation templates using CloudFormation infrastructure as code generator (IaC generator).",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/aws-samples/sample-tool-for-importing-existing-AWS-SCPs-and-RCPs",
    license='MIT-0',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        'Natural Language :: English',
        "Operating System :: OS Independent",
        "Private :: Do not Upload"
    ],
    entry_points={"console_scripts": "policy-importer=scp_and_rcp_import_tool.main:validate_policies_from_organizations"},
    python_requires=">=3.10",
    include_package_data=True,
)