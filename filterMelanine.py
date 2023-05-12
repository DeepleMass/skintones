# filters melanine out by retaining pixels having a red color hue
# 14.11.2022 Nicolas Windt - Bundeskriminalamt

from os import walk, path

from os.path import isfile, split, splitext, join

from PIL import Image

from multiprocessing import Process, Queue

from numpy import exp, array

import csv

__debug = False
__multiproc = True
__sigmoid = True
#######################################  sigmoid #################################
##################################################################################

def sigmoid_int(value :int, offset : float = 0.0, steepness: float = 1.0 ):
	'''
	computes the sigmoid function on integer using offset and steepnes
	'''
	# compute the sigmoid value
	return 1.0 / (1.0 + exp(steepness*(-value+offset)))

###############################  melanine filter #################################
##################################################################################

def melanineFilter(image: Image):
	'''
	This function set all image pixels for which hue is not red (245 < hue < 10)
	recomandation from NIST Jevgeni B.Sirotin: 0 < hue < 70, 6 < value < 34
	Parameter:
		image: Pil Image in rgb code
		
	Returns
		Pil Imane in rgb code
	'''	
	
	if __debug: 
		image.show()
	# convert the image to hsv
	
	h_im : Image = None
	s_im : Image = None 
	v_im : Image =  None
	h_im, s_im, v_im = image.convert('HSV').split()

	# compute a filter out of hue values where 245 < hue < 10
	# first set the hue and value filter to nothing

	h_filter_lambda = lambda x: 0 < x < 70 # according to above recommendation
	#v_filter_lambda = lambda x: 6 < x < 34 # according to abofe reommandation
	
	# if a sigmoid ist requested as smooth filtering
	if __sigmoid : 
		h_filter_lambda = lambda x : sigmoid_int(x,offset=20,steepness=-1) + sigmoid_int(x,offset=235,steepness=1)
		v_filter_lambda = lambda x : sigmoid_int(x,offset=6,steepness=1)+sigmoid_int(x,offset=200,steepness=-1)-1
		
	# evaluate the filters
	hue_filter = Image.eval(h_im,h_filter_lambda) 
	value_filter = Image.eval(v_im,v_filter_lambda)
	
	# compose both hue an value filter
	image_filter = array(hue_filter) #* array(value_filter) 
	
	if __debug: 
		Image.fromarray(image_filter*255).show()

	# set value to 0 for the non concerned filter
	v_im = Image.fromarray(array(v_im)*image_filter)
	
	# result into the image an return

	new_image= Image.merge('HSV',(h_im, s_im, v_im)).convert('RGB')

	if __debug:
		new_image.show()

	return new_image
	

from argparse import ArgumentParser
##########################  create a completed path ##############################
##################################################################################

def create_completed_path(a_path: path, completion: str="_filtered_by_red"):
	''' 
	insert a completion at the end of a file name

	arguments:
		a_path [Path] : the path where te completion is requested
		completion [str] : the name completion for this file. 
				Default is "filtered_by_red"
	return : the completed path

	example:
		create_completed_path(a_path="path/to/the/file.ext", completion="_beeing_completed"):
		returns path/to/the/file_beeing_completed.ext
	'''	
	# we only do that for a file. Else we pass through
	if not isfile(a_path) : return None
	
	# get base name
	location, filename = split(a_path)
	
	# splitfilename and extension
	basename ,extension = splitext(filename)
	
	# merge extended name and extension
	extended_name = basename + completion + extension
	
	# return the new path
	return path.join( location, extended_name )
	

##########################  process a single image ###############################
##################################################################################

ill_files : list = []

# a helper function to process a single image.
def process_single_image( a_path, completion:str = "_filtered_by_red" ):

		# provide a feed back
		if __debug: 
			print ('[File]', a_path)
		else:
			print(".", end='')
		# open the file if possible
		try:
			image=Image.open(a_path)
			
		except:
			print( "could not open" , a_path)
			print( "aborting")
			ill_files.append("rm " + str(a_path))
			return  

		# provide with a feed back
		if __debug : 	
			print ("opened an", type(image))

		# filter the image
		filtered_image = melanineFilter(image)

		if __debug and False:
			exit()

		# save the result
		if True: 

			#create the completed path
			completed_path = create_completed_path(a_path=a_path, completion = completion)

			try:
				# try to save the file, if possible
				filtered_image.save(completed_path) 

			except BaseException as the_error:
				print ("Error: ", a_path, "," ,the_error)
				# note thefile
				ill_files.append("rm " + str(a_path))
				

############################# recursive processing ###############################
##################################################################################
def process_directory_or_file( directory_or_file: path='.', ):
	'''
	This processes all files recursively in all subfolder found if a folder is given as argumen
	If a file is given, only the file will be processed

	Arguments:
		directory_or_file [Path]: a path that can be a directory or a file
	return : nothing (file are saved here)
	'''
	# if the path leads to a file, so we process and save it directly then return 
	#if isfile(directory_or_file):
	print('')
	for root, directories, files  in walk(directory_or_file):
		#provide a feed back
		if __debug__ :
			print ('[root]', root)

		# generate the path to the files for processing
		absolute_pathes = ( join(root,aFile) for aFile in files )

		# switch for multiprocessing
		if  __multiproc :
			# generate the processes
			processes = ( Process(target=process_single_image, args=(a_file,"_filtered_by_red")) for a_file in absolute_pathes ) 

			# start the processes
			[ a_process.start() for a_process in processes ]

			# we may not join the processes since they don't produce any result
			if False : 
				[ a_process.join() for a_process in processes ]

		else : # this is for single thread processing
			[ process_single_image(a_path) for a_path in absolute_pathes] 
			
		for aDirectory in sorted(directories):
			# we recursively process the directories
			process_directory_or_file(join(root,aDirectory)) 

#a helper to create completed path

############################# main function ######################################
##################################################################################
# main function as a test candy
if __name__ == '__main__':

	thePaser = ArgumentParser(description="Filters out the non melanine(red) pixel from an image")
	
	thePaser.add_argument(
		'-p', '--path',
		metavar='path',
		type=str,
		help='provide a path containing images',
		required=True
	)

	# get the args
	input_args = thePaser.parse_args()

	# instantiate a queue for multiprocessing
	if __multiproc: 
		queue = Queue()

	# process the given path
	process_directory_or_file(input_args.path)
	
	with open("ill_files","w") as illfilespath:
		csv.writer(illfilespath, delimiter=' ').writerow(ill_files)