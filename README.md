# 푸크로(Pucro)

## 실행 파일 빌드 (Windows PowerShell)

```powershell
# 기존 빌드 산출물 정리
Remove-Item -Path build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path dist -Recurse -Force -ErrorAction SilentlyContinue

# 1) 스크립트 직접 빌드
pyinstaller --onefile --noconsole -n "Pucro" .\main.py

# 2) spec 사용(동일 결과)
# pyinstaller .\Pucro.spec
```

> 참고: 예전 문서에 있던 `total.py`/`total.spec`는 현재 엔트리포인트(main.py)로 통합되었습니다.
