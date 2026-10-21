import os
import subprocess
import shutil
import zipfile
import stat

REPO_URL = 'https://github.com/MLDMXM2017/MFF-TDF.git'
CLONE_DIR = 'temp_repo'
DATA_DIR = 'ml/data/raw'

def remove_readonly(func, path, _):
    "Clear the readonly bit and reattempt the removal"
    os.chmod(path, stat.S_IWRITE)
    func(path)

def fetch_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CLONE_DIR):
        shutil.rmtree(CLONE_DIR, onerror=remove_readonly)
        
    print('Cloning repository (sparse)...')
    subprocess.run(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', REPO_URL, CLONE_DIR], check=True)
    subprocess.run(['git', '-C', CLONE_DIR, 'sparse-checkout', 'set', 'data'], check=True)
    
    data_path = os.path.join(CLONE_DIR, 'data')
    zip_files = sorted([f for f in os.listdir(data_path) if f.startswith('Tongue_Image') and f.endswith(('.z01', '.z02', '.z03', '.z04', '.z05', '.zip'))])
    
    if zip_files:
        print('Combining multi-part zip files...')
        combined_zip_path = os.path.join(data_path, 'combined.zip')
        with open(combined_zip_path, 'wb') as outfile:
            for zf in zip_files:
                print(f'  Adding {zf}')
                with open(os.path.join(data_path, zf), 'rb') as infile:
                    outfile.write(infile.read())
        
        print('Extracting combined zip...')
        try:
            with zipfile.ZipFile(combined_zip_path, 'r') as zip_ref:
                zip_ref.extractall(DATA_DIR)
        except Exception as e:
            print('Extraction failed:', e)
            print('Moving zip files to ml/data/raw for manual extraction...')
            # Move the original split zip files so they don't get deleted
            for zf in zip_files:
                shutil.move(os.path.join(data_path, zf), os.path.join(DATA_DIR, zf))
            
    indicators = [f for f in os.listdir(data_path) if 'Physiological_Indicators' in f]
    for ind in indicators:
        shutil.move(os.path.join(data_path, ind), os.path.join(DATA_DIR, ind))
        
    shutil.rmtree(CLONE_DIR, onerror=remove_readonly)
    print(f'Data successfully fetched and placed in {DATA_DIR}.')

if __name__ == '__main__':
    fetch_data()
