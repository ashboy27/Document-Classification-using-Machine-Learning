from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from .models import FileInfo, ClassificationOption
from model.api.file_classification_api import file_classification
import os

class FileUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist('files')
        user_id = 1  # Placeholder for user ID
        
        if not files:
            return Response({"error": "No files provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Get classification options for user or fallback
        options_qs = ClassificationOption.objects.filter(user_id=user_id)
        print(options_qs)
        if options_qs.exists():
            options = list(options_qs.values_list('name', flat=True))
            if len(options) < 3:
                options.extend(['Driver License', 'Passport', 'Invoice', 'Contract'])
        else:
            options = ['Driver License', 'Passport', 'Invoice', 'Contract']

        saved_files = []
        for file in files:
            user_folder = os.path.join('user_files', f'user_{user_id}')
            os.makedirs(user_folder, exist_ok=True)
            file_path = os.path.join(user_folder, file.name)

            with open(file_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # Get AI classification suggestion (don't save to DB yet)
            suggested_classification = file_classification(file_path, options)
            print(f"Suggested classification for {file.name}: {suggested_classification}")
            # Save file info without classification (user will confirm later)
            file_info = FileInfo(
                user_id=user_id,
                file_name=file.name,
                file_path=file_path,
                classification=None  # Will be set when user confirms
            )
            file_info.save()

            saved_files.append({
                "id": file_info.id,
                "file_name": file.name,
                "file_path": file_path,
                "suggested_classification": suggested_classification,
                "classification": suggested_classification  # Show suggested for user confirmation
            })

        return Response({"uploaded_files": saved_files, "options_used": options}, status=status.HTTP_201_CREATED)


class FileListView(APIView):
    def get(self, request, *args, **kwargs):
        user_id = 1
        q = request.query_params.get('q')
        cls = request.query_params.get('classification')
        files_qs = FileInfo.objects.filter(user_id=user_id)
        if q:
            files_qs = files_qs.filter(file_name__icontains=q)
        if cls:
            files_qs = files_qs.filter(classification__icontains=cls)
        files = files_qs.order_by('-uploaded_at')
        data = [
            {
                "id": f.id,
                "file_name": f.file_name,
                "classification": f.classification,
                "uploaded_at": f.uploaded_at,
            }
            for f in files
        ]
        return Response({"files": data})

    def patch(self, request, *args, **kwargs):
        # Update classification for a file (user confirmation)
        file_id = request.data.get('id')
        new_classification = request.data.get('classification')
        user_id = 1  # Placeholder for user ID
        
        if not file_id or not new_classification:
            return Response({"error": "id and classification are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_obj = FileInfo.objects.get(id=file_id, user_id=user_id)
        except FileInfo.DoesNotExist:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Save the user-confirmed classification
        file_obj.classification = new_classification
        file_obj.save()
        
        # Add this classification to the user's options (if not already there)
        if new_classification and new_classification.lower() != "none":
            ClassificationOption.objects.get_or_create(
                user_id=user_id,
                name=new_classification
            )
        
        return Response({"message": "Classification updated", "id": file_obj.id, "classification": file_obj.classification})

    def delete(self, request, *args, **kwargs):
        # Delete a file record (and remove file from disk if present)
        file_id = request.data.get('id') or request.query_params.get('id')
        if not file_id:
            return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_obj = FileInfo.objects.get(id=file_id, user_id=1)
        except FileInfo.DoesNotExist:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)
        # Try to remove the underlying file
        try:
            if file_obj.file_path and os.path.exists(file_obj.file_path):
                os.remove(file_obj.file_path)
        except Exception:
            # Ignore file system errors, still delete DB row
            pass
        file_obj.delete()
        return Response({"message": "File deleted", "id": int(file_id)})


class ClassificationOptionsView(APIView):
    def get(self, request, *args, **kwargs):
        user_id = 1
        qs = ClassificationOption.objects.filter(user_id=user_id)
        if not qs.exists():
            defaults = ['Driver License', 'Passport', 'Invoice', 'Contract']
            for name in defaults:
                ClassificationOption.objects.get_or_create(user_id=user_id, name=name)
            qs = ClassificationOption.objects.filter(user_id=user_id)
        options = list(qs.values_list('name', flat=True))
        return Response({"options": options})