"""Railway build hook.

Cloud model clients are configured through Railway environment variables and do
not require model artifacts to be downloaded during the image build.
"""

print("Cloud model preparation is not required during the Railway build.")
