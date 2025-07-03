# Use an official Nginx image as the base
FROM nginx:stable-alpine

# Copy your HTML and JavaScript files into the Nginx default directory
# The Dockerfile is in ./frontend, so '.' refers to the content of 'frontend/'
COPY . /usr/share/nginx/html

# Expose port 80 (default HTTP port)
EXPOSE 80

# Command to run Nginx (default for nginx image)
CMD ["nginx", "-g", "daemon off;"]