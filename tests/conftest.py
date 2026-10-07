import pytest
from unittest.mock import MagicMock, patch

# 伪造 Docker 客户端，防止测试期间操作真实的容器
@pytest.fixture(autouse=True)
def mock_docker_client():
    with patch("ops.backend.client") as mock_ops_client, \
         patch("doctor.doctor_backend.client") as mock_doctor_client:
        
        # 伪造 ops-backend 的列表返回
        mock_container = MagicMock()
        mock_container.name = "medical-api"
        mock_container.status = "running"
        mock_container.image.tags = ["medical-rewrite:v4"]
        mock_ops_client.containers.list.return_value = [mock_container]
        
        # 伪造 doctor-backend 的列表返回
        mock_doctor_client.containers.list.return_value = [mock_container]
        yield