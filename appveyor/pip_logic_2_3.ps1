function pyver ()
{
    if (python -c 'import sys; is_py2 = sys.version_info[0] < 2; sys.exit(not is_py2)')
        {
        pip install -r appveyor-requirements.txt
        }
    else
        {
        pip install -r appveyor-requirements-py2.txt
        }
}
